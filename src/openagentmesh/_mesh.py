"""AgentMesh: the main entry point for the OpenAgentMesh SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import nats
import pydantic
from nats.aio.client import Client as NatsClient
from nats.js import JetStreamContext
from nats.js.kv import KeyValue
from pydantic import BaseModel

from ._context import KVStore
from ._discovery import DiscoveryMixin
from ._errors import (
    ConnectionFailed,
    HandlerError,
    InvalidInput,
    InvocationMismatch,
    MeshError,
)
from ._handler import HandlerInfo, inspect_handler
from ._invocation import InvocationMixin
from ._local import EmbeddedNats
from ._models import (
    AgentContract,
    AgentSpec,
    CatalogEntry,
)
from ._subjects import (
    compute_error_subject,
    compute_event_subject,
    compute_subject,
)
from ._workspace import Workspace

_log = logging.getLogger("openagentmesh")

_CATALOG_BUCKET = "mesh-catalog"
_REGISTRY_BUCKET = "mesh-registry"
_CONTEXT_BUCKET = "mesh-context"
_ARTIFACTS_BUCKET = "mesh-artifacts"
_CATALOG_KEY = "catalog"

X_MESH_INSTANCE_ID = "X-Mesh-Instance-Id"

_SENTINEL = object()  # marker for "handler takes no positional input"


class AgentMesh(InvocationMixin, DiscoveryMixin):
    """Client and host for OpenAgentMesh agents.

    Use as an async context manager::

        mesh = AgentMesh()

        @mesh.agent(spec)
        async def echo(req: EchoInput) -> EchoOutput: ...

        async with mesh:
            result = await mesh.call("echo", {"message": "hi"})

    For tests and demos::

        async with AgentMesh.local() as mesh:
            ...
    """

    def __init__(self, url: str = "nats://localhost:4222"):
        self._url = url
        self.instance_id: str = uuid.uuid4().hex
        self._nc: NatsClient | None = None
        self._js: JetStreamContext | None = None
        self._catalog_kv: KeyValue | None = None
        self._registry_kv: KeyValue | None = None
        self._context_kv: KeyValue | None = None
        self._artifacts_os: Any | None = None
        self.kv: KVStore | None = None
        self.workspace: Workspace | None = None

        # Registered agents and subscription tracking
        self._agents: dict[str, tuple[AgentSpec, HandlerInfo, AgentContract]] = {}
        self._agent_sources: dict[str, list[Any]] = {}
        self._subscribed: set[str] = set()
        self._subscriptions: list[Any] = []
        self._embedded: EmbeddedNats | None = None
        self._catalog_cache: dict[str, CatalogEntry] = {}
        self._catalog_watcher: Any | None = None
        self._catalog_watcher_task: asyncio.Task | None = None
        self._publisher_tasks: dict[str, asyncio.Task] = {}
        self._watcher_tasks: dict[str, asyncio.Task] = {}
        self._source_subscriptions: list[Any] = []
        self._source_tasks: list[asyncio.Task] = []

    @property
    def url(self) -> str:
        """NATS URL this mesh connects to."""
        return self._url

    def __repr__(self) -> str:
        status = "connected" if self._nc is not None else "disconnected"
        mode = "local" if self._embedded is not None else "remote"
        return f"<AgentMesh url={self._url} mode={mode} status={status} agents={len(self._agents)}>"

    def _with_instance_id(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """Return headers with ``X-Mesh-Instance-Id`` defaulted to this mesh's id.

        User-supplied values for the header are preserved (caller wins).
        """
        result = dict(headers) if headers else {}
        result.setdefault(X_MESH_INSTANCE_ID, self.instance_id)
        return result

    # --- Async context manager ---

    async def __aenter__(self) -> AgentMesh:
        await self._connect()
        await self._ensure_buckets()
        await self._seed_catalog_cache()
        await self._start_catalog_watcher()
        await self._subscribe_pending()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._shutdown()

    # --- Connection (private) ---

    async def _connect(self) -> None:
        if self._nc is not None:
            return
        try:
            self._nc = await nats.connect(
                self._url,
                allow_reconnect=False,
                max_reconnect_attempts=5,
                reconnect_time_wait=1,
                error_cb=self._nats_error_cb,
            )
        except Exception as e:
            raise ConnectionFailed(
                message=f"Could not connect to mesh at {self._url}. Is it running? Try: oam mesh up",
            ) from e
        self._js = self._nc.jetstream()

    async def _nats_error_cb(self, e: Exception) -> None:
        _log.debug("nats: %s", e)

    async def _ensure_buckets(self) -> None:
        assert self._js is not None

        specs = [
            ("_catalog_kv",   _CATALOG_BUCKET,   self._js.key_value,    self._js.create_key_value),
            ("_registry_kv",  _REGISTRY_BUCKET,  self._js.key_value,    self._js.create_key_value),
            ("_context_kv",   _CONTEXT_BUCKET,   self._js.key_value,    self._js.create_key_value),
            ("_artifacts_os", _ARTIFACTS_BUCKET, self._js.object_store, self._js.create_object_store),
        ]
        for attr, bucket, get, create in specs:
            try:
                val = await get(bucket)
            except Exception:
                val = await create(bucket=bucket)
            setattr(self, attr, val)

        self.kv = KVStore(self._context_kv)
        self.workspace = Workspace(self._artifacts_os)

    async def _subscribe_pending(self) -> None:
        """Subscribe any agents not yet subscribed."""
        for name, (_spec, info, contract) in self._agents.items():
            if name not in self._subscribed:
                if info.invocable:
                    await self._subscribe_agent(name, info, contract)
                elif info.streaming:
                    if name not in self._publisher_tasks:
                        task = asyncio.create_task(
                            self._emit_publisher_events(name, info)
                        )
                        self._publisher_tasks[name] = task
                else:
                    # Source-driven or legacy watcher. ADR-0052 sources bind
                    # below; ADR-0042 watchers (no input, no return, no sources)
                    # run a watch loop in the handler body.
                    has_sources = bool(self._agent_sources.get(name))
                    if not has_sources and name not in self._watcher_tasks:
                        task = asyncio.create_task(self._run_watcher(name, info))
                        self._watcher_tasks[name] = task

                # Bind ADR-0052 sources for this agent.
                for src in self._agent_sources.get(name, []):
                    await self._bind_source(name, info, src)

                await self._publish_contract(contract)
                await self._update_catalog(contract, add=True)
                self._catalog_cache[name] = contract.to_catalog_entry()
                self._subscribed.add(name)

    async def _seed_catalog_cache(self) -> None:
        """Populate catalog cache from current KV snapshot (ADR-0047)."""
        assert self._catalog_kv is not None
        try:
            entry = await self._catalog_kv.get(_CATALOG_KEY)
            entries = json.loads(entry.value)
            self._catalog_cache = {
                e["name"]: CatalogEntry.model_validate(e) for e in entries
            }
        except Exception:
            pass

    async def _start_catalog_watcher(self) -> None:
        """Start background task that watches the catalog KV for changes (ADR-0032)."""
        assert self._catalog_kv is not None
        self._catalog_watcher = await self._catalog_kv.watchall()

        async def _watch() -> None:
            try:
                async for entry in self._catalog_watcher:
                    if entry is None or entry.value is None:
                        continue
                    if entry.key != _CATALOG_KEY:
                        continue
                    entries = json.loads(entry.value)
                    self._catalog_cache = {
                        e["name"]: CatalogEntry.model_validate(e) for e in entries
                    }
            except asyncio.CancelledError:
                pass  # normal shutdown: task cancelled by _shutdown()
            except Exception:
                pass  # watcher is best-effort; mesh operates on last known cache

        self._catalog_watcher_task = asyncio.create_task(_watch())

    async def _shutdown(self) -> None:
        # Shutdown ordering: stop inbound watchers first so the catalog cache
        # stops mutating, then cancel background handler tasks, unsubscribe
        # NATS handlers, deregister from the cluster catalog/registry, and
        # finally drain the connection. Every step swallows exceptions because
        # shutdown must always succeed -- a broken connection is the common case.

        # 1. Stop catalog watcher: the KV iterator and its consumer task.
        if self._catalog_watcher is not None:
            with suppress(Exception):
                await self._catalog_watcher.stop()
            self._catalog_watcher = None
        if self._catalog_watcher_task is not None:
            self._catalog_watcher_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._catalog_watcher_task
            self._catalog_watcher_task = None

        # 2. Cancel background watcher handlers (ADR-0042). Two-pass so all
        # tasks receive cancel() before we await any one of them, avoiding
        # serialization of their shutdown latency.
        for task in self._watcher_tasks.values():
            task.cancel()
        for task in self._watcher_tasks.values():
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._watcher_tasks.clear()

        # 3. Cancel publisher emission tasks (ADR-0034). Same two-pass pattern;
        # the publisher's CancelledError branch flushes a final end-of-stream
        # marker on its event subject before the connection is drained.
        for task in self._publisher_tasks.values():
            task.cancel()
        for task in self._publisher_tasks.values():
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._publisher_tasks.clear()

        # 3b. Cancel ADR-0052 source-driven KV watch tasks and unsubscribe
        # source-driven NATS subscriptions.
        for task in self._source_tasks:
            task.cancel()
        for task in self._source_tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._source_tasks.clear()

        for sub in self._source_subscriptions:
            with suppress(Exception):
                await sub.unsubscribe()
        self._source_subscriptions.clear()

        # 4. Unsubscribe invocable-agent subscriptions so the broker stops
        # routing requests to this process before we tear down the registry.
        for sub in self._subscriptions:
            with suppress(Exception):
                await sub.unsubscribe()
        self._subscriptions.clear()

        # 5. Deregister from the cluster: remove each owned agent from the
        # shared catalog (CAS retry inside _update_catalog) and delete its
        # per-agent registry key. Skipped when buckets were never created
        # (connection failed before _ensure_buckets completed).
        if self._catalog_kv and self._registry_kv:
            for name in self._subscribed:
                if name in self._agents:
                    _, _, contract = self._agents[name]
                    with suppress(Exception):
                        await self._update_catalog(contract, add=False)
                    with suppress(Exception):
                        await self._registry_kv.delete(name)

        self._subscribed.clear()

        # 6. Drain the NATS connection so in-flight publishes (including the
        # deregistration writes above) flush before the socket closes. Fall
        # back to a hard close if drain fails (e.g. broker already gone).
        if self._nc and self._nc.is_connected:
            try:
                await self._nc.drain()
            except Exception:
                with suppress(Exception):
                    await self._nc.close()
            self._nc = None

    # --- local() ---

    @staticmethod
    @asynccontextmanager
    async def _new_local() -> AsyncIterator[AgentMesh]:
        embedded = EmbeddedNats()
        await embedded.start()
        mesh = AgentMesh(url=embedded.url)
        mesh._embedded = embedded
        try:
            async with mesh:
                yield mesh
        finally:
            await embedded.stop()

    @asynccontextmanager
    async def _instance_local(self) -> AsyncIterator[AgentMesh]:
        original_url = self._url
        embedded = EmbeddedNats()
        await embedded.start()
        self._url = embedded.url
        self._embedded = embedded
        try:
            async with self:
                yield self
        finally:
            self._embedded = None
            self._url = original_url
            await embedded.stop()

    def local(self_or_cls=None) -> AsyncIterator[AgentMesh]:
        """Embedded NATS for tests and demos.

        Works as both a classmethod (creates a new instance) and an
        instance method (reuses the existing instance with all registered
        agents)::

            # Classmethod: new instance, single-file scripts
            async with AgentMesh.local() as mesh:
                @mesh.agent(spec)
                async def echo(req: EchoInput) -> EchoOutput: ...
                result = await mesh.call("echo", {"message": "hi"})

            # Instance method: reuses existing instance and its agents
            mesh = AgentMesh()
            @mesh.agent(spec)
            async def echo(req: EchoInput) -> EchoOutput: ...

            async with mesh.local():
                result = await mesh.call("echo", {"message": "hi"})
        """
        if self_or_cls is None or isinstance(self_or_cls, type):
            return AgentMesh._new_local()
        return self_or_cls._instance_local()

    # --- Registration ---

    def agent(
        self,
        spec: AgentSpec,
        *,
        sources: list[Any] | None = None,
    ):
        """Decorator to register an async function as a mesh agent.

        Usage::

            spec = AgentSpec(name="echo", description="Echoes messages")

            @mesh.agent(spec)
            async def echo(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=f"Echo: {req.message}")

        Source-driven agents (ADR-0052)::

            @mesh.agent(
                AgentSpec(name="watcher", description="reacts to detections"),
                sources=[mesh.kv_source("wildfire.detection.*")],
            )
            async def watcher(entry: KVEntry[DetectionRecord]) -> None:
                ...
        """

        def decorator(func):
            info = inspect_handler(func)

            subject = compute_subject(spec.name)
            contract = AgentContract(
                name=spec.name,
                description=spec.description,
                version=spec.version,
                subject=subject,
                tags=spec.tags,
                invocable=info.invocable,
                streaming=info.streaming,
                capabilities={"streaming": info.streaming, "invocable": info.invocable},
                input_schema=(
                    info.input_adapter.json_schema() if info.input_adapter else None
                ),
                output_schema=(
                    info.output_adapter.json_schema() if info.output_adapter else None
                ),
                chunk_schema=(
                    info.output_adapter.json_schema()
                    if info.streaming and info.output_adapter
                    else None
                ),
            )
            if info.streaming:
                contract.output_schema = None

            self._agents[spec.name] = (spec, info, contract)
            if sources:
                self._agent_sources[spec.name] = list(sources)
            return func

        return decorator

    # --- Source factories (ADR-0052) ---

    def subject_source(self, subject: str, *, queue_group: str | None = None):
        """Create a NATS subject source (ADR-0052).

        Wildcards (``*``, ``>``) are supported. ``queue_group`` enables
        load-balancing across replicas: at-most-one of N consumers receives
        each message.
        """
        from ._sources import SubjectSource
        return SubjectSource(subject=subject, queue_group=queue_group)

    def kv_source(
        self,
        pattern: str,
        *,
        queue_group: str | None = None,
        on_init: str = "replay",
    ):
        """Create a KV-watch source on the ``mesh-context`` bucket (ADR-0052).

        ``pattern`` is a NATS subject wildcard (``*`` or ``>``). ``on_init``
        controls whether the initial KV snapshot is replayed to the handler:

        - ``"replay"`` (default): every existing entry under the pattern fires
          the handler at agent startup, then live updates continue.
        - ``"skip"``: the initial replay is drained silently; only updates
          observed after the agent starts trigger the handler.

        ``queue_group`` is reserved; v1 raises ``NotImplementedError`` if set.
        """
        if queue_group is not None:
            raise NotImplementedError(
                "queue_group on kv_source requires JetStream-backed consumers; "
                "not implemented in v1. Use CAS-based coordination instead."
            )
        if on_init not in ("replay", "skip"):
            raise ValueError(f"on_init must be 'replay' or 'skip'; got {on_init!r}")
        from ._sources import KVSource
        return KVSource(pattern=pattern, queue_group=queue_group, on_init=on_init)

    # --- Lifecycle ---

    def run(self) -> None:
        """Block until interrupted. Like ``uvicorn.run()``.

        Connects, subscribes agents, and serves requests::

            mesh = AgentMesh()

            @mesh.agent(spec)
            async def echo(req: EchoInput) -> EchoOutput: ...

            mesh.run()
        """

        async def _run_forever():
            async with self:
                with suppress(asyncio.CancelledError):
                    await asyncio.Event().wait()

        with suppress(KeyboardInterrupt):
            asyncio.run(_run_forever())

    # --- Agent subscription ---

    async def _subscribe_agent(
        self, name: str, info: HandlerInfo, contract: AgentContract
    ) -> None:
        subject = contract.subject
        queue = f"q.{name}"

        async def handler(msg: nats.aio.msg.Msg) -> None:
            request_id = ""
            wants_stream = False
            if msg.headers:
                request_id = msg.headers.get("X-Mesh-Request-Id", "")
                wants_stream = msg.headers.get("X-Mesh-Stream") == "true"

            try:
                # Pre-flight verb/shape check (ADR-0047)
                if wants_stream and not info.streaming:
                    raise InvocationMismatch(agent=name, request_id=request_id, message=f"Agent '{name}' does not support streaming. Use call() instead")
                if not wants_stream and info.streaming:
                    raise InvocationMismatch(agent=name, request_id=request_id, message=f"Agent '{name}' is streaming-only. Use stream() instead")

                # Input validation (ADR-0057): caller-fault stops here
                try:
                    if info.input_adapter and msg.data:
                        payload = info.input_adapter.validate_json(msg.data)
                    else:
                        payload = None
                except pydantic.ValidationError as ve:
                    raise InvalidInput(
                        agent=name,
                        request_id=request_id,
                        message=f"Input failed validation for agent '{name}'",
                        details={"errors": ve.errors(include_url=False)},
                    ) from ve

                # Handler execution (ADR-0057): provider-fault is wrapped as HandlerError
                try:
                    if info.streaming:
                        await self._handle_streaming(msg, info, name, request_id, payload)
                    else:
                        await self._handle_responder(msg, info, name, request_id, payload)
                except MeshError:
                    raise
                except Exception as e:
                    raise HandlerError(
                        agent=name,
                        request_id=request_id,
                        message=str(e),
                    ) from e
            except MeshError as e:
                error = e
                if wants_stream:
                    stream_subject = f"mesh.stream.{request_id}"
                    await self._nc.publish(
                        stream_subject,
                        error.to_json(),
                        headers=self._with_instance_id({
                            "X-Mesh-Stream-End": "true",
                            "X-Mesh-Status": "error",
                            "X-Mesh-Request-Id": request_id,
                        }),
                    )
                elif msg.reply:
                    await self._nc.publish(
                        msg.reply,
                        error.to_json(),
                        headers=self._with_instance_id({
                            "X-Mesh-Status": "error",
                            "X-Mesh-Request-Id": request_id,
                        }),
                    )
                await self._nc.publish(
                    compute_error_subject(name),
                    error.to_json(),
                    headers=self._with_instance_id({
                        "X-Mesh-Status": "error",
                        "X-Mesh-Request-Id": request_id,
                    }),
                )

        sub = await self._nc.subscribe(subject, queue=queue, cb=handler)
        self._subscriptions.append(sub)

    async def _handle_responder(
        self,
        msg: nats.aio.msg.Msg,
        info: HandlerInfo,
        agent_name: str,
        request_id: str,
        payload: Any,
    ) -> None:
        if payload is not None:
            result = await info.func(payload)
        else:
            result = await info.func()

        if info.output_adapter and result is not None:
            response_data = info.output_adapter.dump_json(result)
        else:
            response_data = json.dumps(result).encode() if result is not None else b"{}"

        if msg.reply:
            await self._nc.publish(
                msg.reply,
                response_data,
                headers=self._with_instance_id({
                    "X-Mesh-Status": "ok",
                    "X-Mesh-Source": agent_name,
                    "X-Mesh-Request-Id": request_id,
                }),
            )

    async def _handle_streaming(
        self,
        msg: nats.aio.msg.Msg,
        info: HandlerInfo,
        agent_name: str,
        request_id: str,
        payload: Any,
    ) -> None:
        stream_subject = f"mesh.stream.{request_id}"

        gen = info.func(payload) if payload is not None else info.func()
        seq = 0
        async for chunk in gen:
            if info.output_adapter:
                chunk_data = info.output_adapter.dump_json(chunk)
            else:
                chunk_data = json.dumps(chunk).encode()

            await self._nc.publish(
                stream_subject,
                chunk_data,
                headers=self._with_instance_id({
                    "X-Mesh-Stream-Seq": str(seq),
                    "X-Mesh-Stream-End": "false",
                    "X-Mesh-Request-Id": request_id,
                }),
            )
            await self._nc.flush()
            seq += 1

        await self._nc.publish(
            stream_subject,
            b"",
            headers=self._with_instance_id({
                "X-Mesh-Stream-Seq": str(seq),
                "X-Mesh-Stream-End": "true",
                "X-Mesh-Request-Id": request_id,
            }),
        )
        await self._nc.flush()

    # --- Watcher execution (ADR-0042) ---

    async def _run_watcher(self, name: str, info: HandlerInfo) -> None:
        """Run a watcher handler as a background task."""
        with suppress(asyncio.CancelledError):
            await info.func()

    # --- Publisher emission (ADR-0034) ---

    async def _emit_publisher_events(
        self, name: str, info: HandlerInfo
    ) -> None:
        """Run a publisher handler and publish yielded values to its event subject."""
        event_subject = compute_event_subject(name)

        gen = info.func()
        seq = 0
        try:
            async for chunk in gen:
                if info.output_adapter:
                    data = info.output_adapter.dump_json(chunk)
                else:
                    data = json.dumps(chunk).encode()

                await self._nc.publish(
                    event_subject,
                    data,
                    headers=self._with_instance_id({
                        "X-Mesh-Stream-Seq": str(seq),
                        "X-Mesh-Stream-End": "false",
                    }),
                )
                seq += 1

            await self._nc.publish(
                event_subject,
                b"",
                headers=self._with_instance_id({
                    "X-Mesh-Stream-Seq": str(seq),
                    "X-Mesh-Stream-End": "true",
                }),
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await self._nc.publish(
                    event_subject,
                    b"",
                    headers=self._with_instance_id({
                        "X-Mesh-Stream-Seq": str(seq),
                        "X-Mesh-Stream-End": "true",
                    }),
                )
        except Exception as e:
            _log.warning("Publisher '%s' failed: %s", name, e)
            error = HandlerError(message=str(e), agent=name)
            try:
                await self._nc.publish(
                    event_subject,
                    error.to_json(),
                    headers=self._with_instance_id({
                        "X-Mesh-Stream-End": "true",
                        "X-Mesh-Status": "error",
                    }),
                )
                await self._nc.publish(
                    compute_error_subject(name),
                    error.to_json(),
                    headers=self._with_instance_id({"X-Mesh-Status": "error"}),
                )
            except Exception:
                pass

    # --- Source binding (ADR-0052) ---

    async def _bind_source(self, name: str, info: HandlerInfo, source: Any) -> None:
        """Subscribe an agent's source. Tracks teardown handles."""
        from ._sources import KVSource, SubjectSource

        if isinstance(source, SubjectSource):
            await self._bind_subject_source(name, info, source)
        elif isinstance(source, KVSource):
            await self._bind_kv_source(name, info, source)
        else:
            raise TypeError(
                f"Unknown source type for agent '{name}': {type(source).__name__}"
            )

    async def _bind_subject_source(self, name: str, info: HandlerInfo, source: Any) -> None:

        async def cb(msg):
            try:
                payload = self._build_source_input(
                    info,
                    raw_value=msg.data,
                    source_kind="subject",
                    subject=msg.subject,
                    headers=dict(msg.headers or {}),
                )
                await info.func(payload) if payload is not _SENTINEL else await info.func()
            except Exception as e:
                _log.warning("Source handler for '%s' raised: %s", name, e)

        sub = await self._nc.subscribe(
            source.subject,
            queue=source.queue_group,
            cb=cb,
        )
        self._source_subscriptions.append(sub)

    async def _bind_kv_source(self, name: str, info: HandlerInfo, source: Any) -> None:
        watcher = await self._context_kv.watch(source.pattern)
        task = asyncio.create_task(
            self._drain_kv_source(name, info, source, watcher)
        )
        self._source_tasks.append(task)

    async def _drain_kv_source(self, name: str, info: HandlerInfo, source: Any, watcher: Any) -> None:
        skip_initial = source.on_init == "skip"
        init_done = False
        try:
            async for entry in watcher:
                if entry is None:
                    init_done = True
                    continue
                if entry.value is None:
                    continue
                if skip_initial and not init_done:
                    continue

                op = (
                    "DELETE"
                    if str(getattr(entry, "operation", "PUT")).upper().endswith("DELETE")
                    else "PUT"
                )
                try:
                    payload = self._build_source_input(
                        info,
                        raw_value=entry.value,
                        source_kind="kv",
                        kv_key=entry.key,
                        kv_revision=entry.revision,
                        kv_operation=op,
                    )
                    await info.func(payload) if payload is not _SENTINEL else await info.func()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    _log.warning("KV source handler for '%s' raised on key %r: %s", name, entry.key, e)
        except asyncio.CancelledError:
            pass
        finally:
            with suppress(Exception):
                await watcher.stop()

    def _build_source_input(
        self,
        info: HandlerInfo,
        *,
        raw_value: bytes,
        source_kind: str,
        subject: str | None = None,
        headers: dict[str, str] | None = None,
        kv_key: str | None = None,
        kv_revision: int | None = None,
        kv_operation: str | None = None,
    ) -> Any:
        """Build the payload to pass to a source handler based on its type hint."""
        from ._context import KVEntry
        from ._sources import MeshMessage

        kind = info.source_param_kind
        model_cls = info.source_param_model

        def _validate_or_pass(value: bytes, cls: type | None) -> Any:
            if cls is None or cls is bytes:
                return value
            if isinstance(cls, type) and issubclass(cls, BaseModel):
                return cls.model_validate_json(value)
            return value

        if kind == "none":
            return _SENTINEL

        if kind == "bytes":
            return raw_value

        if kind == "model":
            return _validate_or_pass(raw_value, model_cls)

        if kind == "kv_entry":
            value = _validate_or_pass(raw_value, model_cls)
            return KVEntry(
                key=kv_key or "",
                value=value,
                revision=kv_revision or 0,
                operation=kv_operation or "PUT",  # type: ignore[arg-type]
            )

        if kind == "mesh_message":
            payload = _validate_or_pass(raw_value, model_cls)
            return MeshMessage(
                subject=subject or "",
                headers=headers or {},
                payload=payload,
            )

        return _SENTINEL

    # --- Capability checks (ADR-0047) ---

    # (operation, invocable, streaming) → error suffix. Missing key = allowed.
    _CAPABILITY_ERRORS: dict[tuple[str, bool, bool], str] = {
        ("call", False, True):      "is a publisher and cannot be called. Subscribe to its events instead",
        ("call", False, False):     "is a background task and cannot be called",
        ("call", True, True):       "is streaming-only. Use stream() instead",
        ("stream", False, True):    "is a publisher and cannot be streamed. Subscribe to its events instead",
        ("stream", False, False):   "is a background task and cannot be streamed",
        ("stream", True, False):    "does not support streaming. Use call() instead",
        ("send", False, True):      "is a publisher and cannot be sent to. Subscribe to its events instead",
        ("send", False, False):     "is a background task and cannot be sent to",
        ("subscribe", True, True):  "streams responses to requests. Use stream() instead",
        ("subscribe", True, False): "does not publish events. Use call() instead",
        ("subscribe", False, False): "is a background task and does not publish events",
    }

    def _check_capability(self, name: str, operation: str) -> None:
        if name in self._agents:
            _, _, contract = self._agents[name]
            caps = (contract.invocable, contract.streaming)
        else:
            entry = self._catalog_cache.get(name)
            if entry is None:
                return
            caps = (entry.invocable, entry.streaming)
        msg = self._CAPABILITY_ERRORS.get((operation, *caps))
        if msg:
            raise InvocationMismatch(agent=name, message=f"Agent '{name}' {msg}")


    # --- Internal helpers ---

    def _resolve_subject(self, name: str) -> str:
        return compute_subject(name)

    async def _resolve_event_subject(self, name: str) -> str:
        """Resolve an agent name to its event subject.

        Raises NotFound (a MeshError subclass) if the agent is unknown locally
        and absent from the registry. Without this check subscribe(agent=...)
        would block forever on a subject that nobody publishes to.
        """
        if name in self._agents or name in self._catalog_cache:
            return compute_event_subject(name)
        await self.contract(name)
        return compute_event_subject(name)

    @staticmethod
    def _serialize_payload(payload: Any) -> bytes:
        if payload is None:
            return b""
        if isinstance(payload, BaseModel):
            return payload.model_dump_json().encode()
        if isinstance(payload, bytes):
            return payload
        return json.dumps(payload).encode()

    async def _publish_contract(self, contract: AgentContract) -> None:
        assert self._registry_kv is not None
        await self._registry_kv.put(contract.name, contract.to_registry_json().encode())

    async def _update_catalog(self, contract: AgentContract, *, add: bool) -> None:
        assert self._catalog_kv is not None
        entry_dict = contract.to_catalog_entry().model_dump()

        from nats.js.errors import KeyNotFoundError

        for _ in range(10):
            try:
                kv_entry = await self._catalog_kv.get(_CATALOG_KEY)
                current: list[dict] = json.loads(kv_entry.value)
                revision = kv_entry.revision
            except (KeyNotFoundError, Exception):
                current = []
                revision = 0

            current = [e for e in current if e.get("name") != contract.name]
            if add:
                current.append(entry_dict)

            new_data = json.dumps(current).encode()

            try:
                if revision == 0:
                    await self._catalog_kv.create(_CATALOG_KEY, new_data)
                else:
                    await self._catalog_kv.update(_CATALOG_KEY, new_data, last=revision)
                return
            except Exception:
                await asyncio.sleep(0.01)
                continue

        raise RuntimeError("Failed to update catalog after 10 CAS retries")
