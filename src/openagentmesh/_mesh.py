"""AgentMesh: the main entry point for the OpenAgentMesh SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Literal

import nats
import pydantic
from nats.aio.client import Client as NatsClient
from nats.aio.msg import Msg
from nats.js import JetStreamContext
from nats.js.kv import KeyValue
from pydantic import BaseModel

from ._auth import build_tls_context, is_auth_error, resolve_creds
from ._context import KVStore
from ._discovery import DiscoveryMixin
from ._errors import (
    ConnectionDenied,
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
    DeathNotice,
    LogEvent,
)
from ._observe import GLOBAL_KEY, LEVELS, Observe, _parse_level
from ._subjects import (
    compute_death_subject,
    compute_error_subject,
    compute_event_subject,
    compute_log_subject,
    compute_subject,
)
from ._usage import (
    X_MESH_USAGE,
    Usage,
    begin_usage_capture,
    end_usage_capture,
)
from ._workspace import Workspace

_log = logging.getLogger("openagentmesh")

_CATALOG_BUCKET = "mesh-catalog"
_REGISTRY_BUCKET = "mesh-registry"
_CONTEXT_BUCKET = "mesh-context"
_ARTIFACTS_BUCKET = "mesh-artifacts"
_INSTANCES_BUCKET = "mesh-instances"
_OBSERVE_BUCKET = "mesh-observability"
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

    def __init__(
        self,
        url: str = "nats://localhost:4222",
        *,
        creds: str | None = None,
        tls_cert: str | None = None,
        tls_key: str | None = None,
        tls_ca: str | None = None,
    ):
        self._url = url
        self._creds = creds
        self._tls_cert = tls_cert
        self._tls_key = tls_key
        self._tls_ca = tls_ca
        self.instance_id: str = uuid.uuid4().hex
        self._nc: NatsClient | None = None
        self._js: JetStreamContext | None = None
        self._catalog_kv: KeyValue | None = None
        self._registry_kv: KeyValue | None = None
        self._instances_kv: KeyValue | None = None
        self._observe_kv: KeyValue | None = None
        self._context_kv: KeyValue | None = None
        self._artifacts_os: Any | None = None
        self._kv: KVStore | None = None
        self._workspace: Workspace | None = None

        # Registered agents and subscription tracking
        self._agents: dict[str, tuple[AgentSpec, HandlerInfo, AgentContract]] = {}
        self._agent_sources: dict[str, list[Any]] = {}
        self._subscribed: set[str] = set()
        self._subscriptions: dict[str, Any] = {}
        self._embedded: EmbeddedNats | None = None
        self._catalog_cache: dict[str, CatalogEntry] = {}
        self._catalog_watcher: Any | None = None
        self._catalog_watcher_task: asyncio.Task | None = None
        self._publisher_tasks: dict[str, asyncio.Task] = {}
        self._watcher_tasks: dict[str, asyncio.Task] = {}
        self._source_subscriptions: dict[str, list[Any]] = {}
        self._source_tasks: dict[str, list[asyncio.Task]] = {}
        # Lifecycle gates (ADR-0055): per-agent condition, current on/off
        # state, and the background watcher driving transitions.
        self._agent_gates: dict[str, Any] = {}
        self._gate_state: dict[str, bool] = {}
        self._gate_watch_tasks: dict[str, asyncio.Task] = {}
        self._gate_subscriptions: dict[str, Any] = {}
        # In-flight handler tasks for gated agents. Gated handlers run as
        # tasks (not inline in the subscription callback) so deactivation can
        # unsubscribe immediately and drain them separately — cancelling
        # nats-py's Subscription.drain() mid-flush corrupts the client's
        # pong futures and kills its read loop.
        self._inflight_tasks: dict[str, set[asyncio.Task]] = {}
        # Subjects the server denied us on (ADR-0038): violations arrive
        # asynchronously, so call sites consult this to turn a bare timeout
        # into a ConnectionDenied.
        self._denied_subjects: set[str] = set()
        # Agent names last written to the mesh-instances record (ADR-0016).
        self._instance_record: list[str] = []
        # Observability (ADR-0048): cached level config, updated by KV watch.
        self._observe_ns: Observe | None = None
        self._observe_config: dict[str, str] = {}
        self._observe_watcher: Any | None = None
        self._observe_watcher_task: asyncio.Task | None = None

    @property
    def url(self) -> str:
        """NATS URL this mesh connects to."""
        return self._url

    @property
    def _conn(self) -> NatsClient:
        """The live NATS connection; only valid after connect."""
        if self._nc is None:
            raise ConnectionFailed(message="Mesh is not connected; use 'async with mesh:' first")
        return self._nc

    @property
    def kv(self) -> KVStore:
        """Shared KV store (``mesh-context`` bucket). Available once connected."""
        if self._kv is None:
            raise ConnectionFailed(message="Mesh is not connected; use 'async with mesh:' first")
        return self._kv

    @property
    def workspace(self) -> Workspace:
        """Object Store workspace (``mesh-artifacts`` bucket). Available once connected."""
        if self._workspace is None:
            raise ConnectionFailed(message="Mesh is not connected; use 'async with mesh:' first")
        return self._workspace

    @property
    def observe(self) -> Observe:
        """Observability namespace (ADR-0048): tail logs, manage levels."""
        if self._observe_ns is None:
            self._observe_ns = Observe(self)
        return self._observe_ns

    @property
    def _observe_kv_required(self) -> KeyValue:
        if self._observe_kv is None:
            raise ConnectionFailed(message="Mesh is not connected; use 'async with mesh:' first")
        return self._observe_kv

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
        await self._start_observe_watcher()
        await self._subscribe_pending()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._shutdown()

    # --- Connection (private) ---

    async def _connect(self) -> None:
        if self._nc is not None:
            return

        # A local mesh stays open (ADR-0038 §2): no ambient OAM_CREDS/.oam-url pickup.
        creds = self._creds if self._embedded is not None else resolve_creds(self._creds)
        if creds is not None and not Path(creds).is_file():
            raise ConnectionFailed(
                message=f"Credentials file not found: {creds}",
            )
        options: dict[str, Any] = {}
        if creds is not None:
            options["user_credentials"] = creds
        tls_context = build_tls_context(
            tls_cert=self._tls_cert, tls_key=self._tls_key, tls_ca=self._tls_ca
        )
        if tls_context is not None:
            options["tls"] = tls_context

        try:
            self._nc = await nats.connect(
                self._url,
                # The connection name lets the health monitor correlate
                # disconnect advisories back to this host (ADR-0016).
                name=f"oam-host-{self.instance_id}",
                allow_reconnect=False,
                max_reconnect_attempts=5,
                reconnect_time_wait=1,
                error_cb=self._nats_error_cb,
                **options,
            )
        except Exception as e:
            if is_auth_error(e):
                raise ConnectionDenied(
                    message=(
                        f"Mesh at {self._url} rejected the connection: {e}. "
                        + (
                            f"Credentials used: {creds}"
                            if creds
                            else "No credentials were presented; the server requires auth "
                            "(creds=, OAM_CREDS, or a creds field in .oam-url)"
                        )
                    ),
                ) from e
            raise ConnectionFailed(
                message=f"Could not connect to mesh at {self._url}. Is it running? Try: oam mesh up",
            ) from e
        self._js = self._nc.jetstream()

    async def _nats_error_cb(self, e: Exception) -> None:
        if is_auth_error(e):
            _log.warning("nats connection_denied: %s", e)
            match = re.search(r'violation for (?:publish|subscription) to "([^"]+)"', str(e))
            if match:
                self._denied_subjects.add(match.group(1).lower())
        else:
            _log.debug("nats: %s", e)

    async def _ensure_buckets(self) -> None:
        assert self._js is not None

        specs = [
            ("_catalog_kv",   _CATALOG_BUCKET,   self._js.key_value,    self._js.create_key_value),
            ("_registry_kv",  _REGISTRY_BUCKET,  self._js.key_value,    self._js.create_key_value),
            ("_instances_kv", _INSTANCES_BUCKET, self._js.key_value,    self._js.create_key_value),
            ("_observe_kv",   _OBSERVE_BUCKET,   self._js.key_value,    self._js.create_key_value),
            ("_context_kv",   _CONTEXT_BUCKET,   self._js.key_value,    self._js.create_key_value),
            ("_artifacts_os", _ARTIFACTS_BUCKET, self._js.object_store, self._js.create_object_store),
        ]
        for attr, bucket, get, create in specs:
            try:
                val = await get(bucket)
            except Exception:
                val = await create(bucket=bucket)
            setattr(self, attr, val)

        assert self._context_kv is not None and self._artifacts_os is not None
        self._kv = KVStore(self._context_kv)
        self._workspace = Workspace(self._artifacts_os)

    async def _subscribe_pending(self) -> None:
        """Subscribe any agents not yet subscribed."""
        for name, (_spec, _info, contract) in self._agents.items():
            if name not in self._subscribed:
                gate = self._agent_gates.get(name)
                if gate is None:
                    await self._activate_agent(name)
                else:
                    # Gated agent (ADR-0055): register in the catalog but let
                    # the gate decide whether to subscribe.
                    await self._start_gate(name, gate)

                await self._publish_contract(contract)
                await self._update_catalog(contract, add=True)
                self._catalog_cache[name] = contract.to_catalog_entry()
                self._subscribed.add(name)
                await self._publish_log(
                    name, "info", "agent_registered",
                    message=f"Agent '{name}' registered",
                )

        await self._record_instance()

    async def _activate_agent(self, name: str) -> None:
        """Bring an agent online: RPC subscription, background tasks, sources.

        Idempotent — a second call while online is a no-op, which absorbs
        the gate's get-then-watch startup race (ADR-0055).
        """
        if self._gate_state.get(name):
            return
        _spec, info, contract = self._agents[name]

        if info.invocable:
            if name not in self._subscriptions:
                await self._subscribe_agent(name, info, contract)
        elif info.streaming:
            if name not in self._publisher_tasks:
                task = asyncio.create_task(self._emit_publisher_events(name, info))
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

        self._gate_state[name] = True

    async def _deactivate_agent(self, name: str, drain_timeout: float = 30.0) -> None:
        """Take an agent offline: drain in-flight handlers, then unsubscribe.

        The RPC subscription is drained (leaves the queue group, lets
        in-flight handlers complete, bounded by ``drain_timeout``); source
        subscriptions and background tasks are torn down.
        """
        if not self._gate_state.get(name):
            return
        self._gate_state[name] = False

        sub = self._subscriptions.pop(name, None)
        if sub is not None:
            # Leave the queue group first (new requests stop routing here),
            # then wait out our own in-flight handler tasks. Never
            # Subscription.drain(): it is not cancellation-safe (see
            # _inflight_tasks in __init__).
            with suppress(Exception):
                await sub.unsubscribe()
            pending = {t for t in self._inflight_tasks.get(name, ()) if not t.done()}
            if pending:
                _done, still_pending = await asyncio.wait(pending, timeout=drain_timeout)
                for task in still_pending:
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task

        for tasks_map in (self._publisher_tasks, self._watcher_tasks):
            task = tasks_map.pop(name, None)
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

        for task in self._source_tasks.pop(name, []):
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        for sub in self._source_subscriptions.pop(name, []):
            with suppress(Exception):
                await sub.unsubscribe()

    # --- Lifecycle gates (ADR-0055) ---

    async def _start_gate(self, name: str, gate: Any) -> None:
        """Evaluate a gate's current signal, then watch it for changes."""
        from ._lifecycle import KVCondition, SubjectCondition

        state = bool(gate.initial)
        if isinstance(gate, KVCondition):
            from nats.js.errors import KeyDeletedError, KeyNotFoundError

            assert self._context_kv is not None
            try:
                entry = await self._context_kv.get(gate.key)
                state = bool(gate.predicate(entry.value))
            except (KeyNotFoundError, KeyDeletedError):
                state = bool(gate.predicate(None))
            except Exception as e:
                # Fall back to `initial` (ADR-0055 amendment) — e.g. the
                # connection's credentials cannot read the context bucket.
                _log.warning("Gate for '%s': initial read failed (%s)", name, e)

        if state:
            await self._activate_agent(name)

        if name in self._gate_watch_tasks:
            return
        if isinstance(gate, KVCondition):
            task = asyncio.create_task(self._watch_kv_gate(name, gate))
            self._gate_watch_tasks[name] = task
        elif isinstance(gate, SubjectCondition):
            async def _on_signal(msg: Msg) -> None:
                await self._apply_gate(name, gate, msg.data or b"")

            gate_sub = await self._conn.subscribe(gate.subject, cb=_on_signal)
            self._gate_subscriptions[name] = gate_sub
        else:
            raise TypeError(
                f"Unknown condition type for agent '{name}': {type(gate).__name__}"
            )

    async def _watch_kv_gate(self, name: str, gate: Any) -> None:
        assert self._context_kv is not None
        watcher = await self._context_kv.watch(gate.key, ignore_deletes=False)
        try:
            async for entry in watcher:
                if entry is None:  # end of initial replay
                    continue
                op = str(getattr(entry, "operation", "PUT") or "PUT").upper()
                value = None if op.endswith(("DELETE", "PURGE")) else entry.value
                await self._apply_gate(name, gate, value)
        except asyncio.CancelledError:
            pass
        finally:
            with suppress(Exception):
                await watcher.stop()

    async def _apply_gate(self, name: str, gate: Any, value: Any) -> None:
        try:
            state = bool(gate.predicate(value))
        except Exception as e:
            _log.warning("Gate predicate for '%s' raised: %s", name, e)
            return
        if state and not self._gate_state.get(name):
            await self._activate_agent(name)
            await self._publish_log(
                name, "info", "agent_activated",
                message=f"Agent '{name}' came online (lifecycle gate opened)",
            )
        elif not state and self._gate_state.get(name):
            await self._deactivate_agent(name, gate.drain_timeout)
            await self._publish_log(
                name, "info", "agent_deactivated",
                message=f"Agent '{name}' went offline (lifecycle gate closed)",
            )

    async def _record_instance(self) -> None:
        """Write this host's instance → agents mapping (ADR-0016).

        The health monitor uses it to correlate a disconnect advisory with
        the agents the dead host was serving. Idempotent; only writes when
        the served set changed.
        """
        if not self._subscribed or self._instances_kv is None:
            return
        record = sorted(self._subscribed)
        if record == self._instance_record:
            return
        try:
            await self._instances_kv.put(
                self.instance_id, json.dumps({"agents": record}).encode()
            )
        except Exception as e:
            # Credentials minted before mesh-instances existed can't write it.
            # Degrade: the mesh works, but the monitor can't correlate this
            # host's death (no advisory-driven cleanup for its agents).
            _log.warning(
                "could not record instance liveness (stale credentials?): %s", e
            )
        self._instance_record = record

    async def _seed_catalog_cache(self) -> None:
        """Populate catalog cache from current KV snapshot (ADR-0047)."""
        assert self._catalog_kv is not None
        try:
            entry = await self._catalog_kv.get(_CATALOG_KEY)
            entries = json.loads(entry.value or b"[]")
            self._catalog_cache = {
                e["name"]: CatalogEntry.model_validate(e) for e in entries
            }
        except Exception:
            pass

    async def _start_catalog_watcher(self) -> None:
        """Start background task that watches the catalog KV for changes (ADR-0032)."""
        assert self._catalog_kv is not None
        watcher = await self._catalog_kv.watchall()
        self._catalog_watcher = watcher

        async def _watch() -> None:
            try:
                async for entry in watcher:
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

    async def _start_observe_watcher(self) -> None:
        """Watch the mesh-observability KV bucket for level changes (ADR-0048).

        The watcher replays current keys on start (seeding the cache) and then
        streams updates, so runtime `oam observe set` calls apply without a
        restart. Best-effort: on stale credentials the mesh runs at default
        levels rather than failing.
        """
        if self._observe_kv is None:
            return
        try:
            watcher = await self._observe_kv.watchall()
        except Exception as e:
            _log.warning("could not watch observability config (stale credentials?): %s", e)
            return
        self._observe_watcher = watcher

        async def _watch() -> None:
            try:
                async for entry in watcher:
                    if entry is None:
                        continue
                    level = _parse_level(entry.value)
                    if level is None:
                        self._observe_config.pop(entry.key, None)
                    else:
                        self._observe_config[entry.key] = level
            except asyncio.CancelledError:
                pass  # normal shutdown
            except Exception:
                pass  # best-effort; mesh keeps last known levels

        self._observe_watcher_task = asyncio.create_task(_watch())

    def _observe_threshold(self, agent: str) -> int:
        """Effective numeric log threshold: per-agent > global > info."""
        level = (
            self._observe_config.get(agent)
            or self._observe_config.get(GLOBAL_KEY)
            or "info"
        )
        return LEVELS.get(level, LEVELS["info"])

    async def _publish_log(
        self,
        agent: str,
        level: Literal["debug", "info", "warn", "error"],
        event: str,
        *,
        request_id: str = "",
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Publish a structured log event (ADR-0048). Never fails the caller."""
        if LEVELS[level] < self._observe_threshold(agent):
            return
        log_event = LogEvent(
            level=level,
            agent=agent,
            event=event,
            request_id=request_id,
            message=message,
            data=data or {},
        )
        try:
            await self._conn.publish(
                compute_log_subject(agent),
                log_event.model_dump_json().encode(),
                headers=self._with_instance_id(),
            )
        except Exception as e:
            _log.debug("could not publish log event: %s", e)

    async def _publish_usage(
        self, agent: str, request_id: str, usage: Usage | None
    ) -> None:
        """Publish the ``usage_reported`` observe event (ADR-0023).

        Only agents whose handlers actually called ``report_usage()`` emit
        it, so the default-level zero-cost property of ADR-0048 holds for
        everyone else.
        """
        if usage is None:
            return
        await self._publish_log(
            agent, "info", "usage_reported",
            request_id=request_id,
            data=usage.model_dump(exclude_none=True),
        )

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

        # 1b. Stop the observability config watcher (ADR-0048), same pattern.
        if self._observe_watcher is not None:
            with suppress(Exception):
                await self._observe_watcher.stop()
            self._observe_watcher = None
        if self._observe_watcher_task is not None:
            self._observe_watcher_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._observe_watcher_task
            self._observe_watcher_task = None

        # 1c. Deregistration log events (ADR-0048) while the connection is
        # still fully live; _publish_log is itself best-effort.
        for name in self._subscribed:
            with suppress(Exception):
                await self._publish_log(
                    name, "info", "agent_deregistered",
                    message=f"Agent '{name}' deregistered",
                )

        # 1d. Stop lifecycle-gate watchers (ADR-0055) before any of the
        # subscriptions and tasks they manage are torn down, so no gate
        # transition races the teardown below.
        for task in self._gate_watch_tasks.values():
            task.cancel()
        for task in self._gate_watch_tasks.values():
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._gate_watch_tasks.clear()
        for sub in self._gate_subscriptions.values():
            with suppress(Exception):
                await sub.unsubscribe()
        self._gate_subscriptions.clear()

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
        all_source_tasks = [t for tasks in self._source_tasks.values() for t in tasks]
        for task in all_source_tasks:
            task.cancel()
        for task in all_source_tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._source_tasks.clear()

        for subs in self._source_subscriptions.values():
            for sub in subs:
                with suppress(Exception):
                    await sub.unsubscribe()
        self._source_subscriptions.clear()

        # 4. Unsubscribe invocable-agent subscriptions so the broker stops
        # routing requests to this process before we tear down the registry.
        for sub in self._subscriptions.values():
            with suppress(Exception):
                await sub.unsubscribe()
        self._subscriptions.clear()
        self._gate_state.clear()

        # 4b. Cancel any in-flight gated-handler tasks (ADR-0055) still
        # running after their subscriptions are gone.
        leftover = [t for tasks in self._inflight_tasks.values() for t in tasks if not t.done()]
        for task in leftover:
            task.cancel()
        for task in leftover:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._inflight_tasks.clear()

        # 5. Deregister from the cluster (ADR-0016): drop this host's
        # instance record first so the survivor scan below (ours and the
        # health monitor's) no longer counts us, then remove each owned agent
        # that no other live instance serves — removing it while a replica
        # lives would blind discovery to a healthy agent. Fully-departed
        # agents get a graceful death notice. Skipped when buckets were never
        # created (connection failed before _ensure_buckets completed).
        if self._catalog_kv and self._registry_kv:
            if self._instances_kv is not None and self._instance_record:
                with suppress(Exception):
                    await self._instances_kv.delete(self.instance_id)
            survivors: set[str] = set()
            with suppress(Exception):
                survivors = await self._agents_served_by_live_instances()
            for name in self._subscribed:
                if name in self._agents and name not in survivors:
                    with suppress(Exception):
                        await self._deregister_agent_record(name)
                    with suppress(Exception):
                        notice = DeathNotice(
                            agent=name,
                            reason="graceful_shutdown",
                            instance_id=self.instance_id,
                        )
                        await self._conn.publish(
                            compute_death_subject(name),
                            notice.model_dump_json().encode(),
                        )

        self._subscribed.clear()
        self._instance_record = []

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
    async def _local_monitor(embedded: EmbeddedNats) -> AsyncIterator[None]:
        """Run the ADR-0016 health monitor beside an embedded server."""
        from ._monitor import HealthMonitor

        monitor = HealthMonitor(embedded.url, sys_url=embedded.sys_url)
        # Like the local mesh itself, the monitor's app connection must not
        # pick up ambient OAM_CREDS/.oam-url against an embedded server
        # (ADR-0038 §2).
        monitor._mesh._embedded = embedded
        await monitor.start()
        try:
            yield
        finally:
            await monitor.stop()

    @staticmethod
    @asynccontextmanager
    async def _new_local() -> AsyncIterator[AgentMesh]:
        embedded = EmbeddedNats()
        await embedded.start()
        mesh = AgentMesh(url=embedded.url)
        mesh._embedded = embedded
        try:
            async with AgentMesh._local_monitor(embedded), mesh:
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
            async with AgentMesh._local_monitor(embedded), self:
                yield self
        finally:
            self._embedded = None
            self._url = original_url
            await embedded.stop()

    def local(self_or_cls=None) -> AbstractAsyncContextManager[AgentMesh]:
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
        active_when: Any | None = None,
        mcp: bool | None = None,
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

        Lifecycle-gated agents (ADR-0055) subscribe only while the
        condition holds; the contract stays in the catalog either way::

            @mesh.agent(
                AgentSpec(name="coordinator", description="active-incident work"),
                active_when=mesh.kv_condition("incident.mode", lambda v: v == b'"active"'),
            )
            async def coordinator(brief: Brief) -> Assignment:
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
            contract.mcp = mcp

            self._agents[spec.name] = (spec, info, contract)
            if sources:
                self._agent_sources[spec.name] = list(sources)
            if active_when is not None:
                self._agent_gates[spec.name] = active_when
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
        on_init: Literal["replay", "skip"] = "replay",
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

    # --- Condition factories (ADR-0055) ---

    def kv_condition(
        self,
        key: str,
        predicate: Callable[[bytes | None], bool],
        *,
        initial: bool = False,
        drain_timeout: float = 30.0,
    ):
        """Create a lifecycle gate on a ``mesh-context`` KV key (ADR-0055).

        The predicate receives the key's raw ``bytes`` value (``None`` when
        absent or deleted); the agent is subscribed only while it returns
        True. On gate close, in-flight handlers drain for up to
        ``drain_timeout`` seconds before the agent unsubscribes.
        """
        from ._lifecycle import KVCondition
        return KVCondition(
            key=key, predicate=predicate, initial=initial, drain_timeout=drain_timeout
        )

    def subject_condition(
        self,
        subject: str,
        predicate: Callable[[bytes], bool],
        *,
        initial: bool = False,
        drain_timeout: float = 30.0,
    ):
        """Create a lifecycle gate on a plain NATS subject (ADR-0055).

        Each message on ``subject`` re-evaluates the predicate against the
        payload bytes; the agent's state follows the most recent verdict.
        ``initial`` is the state before the first message arrives.
        """
        from ._lifecycle import SubjectCondition
        return SubjectCondition(
            subject=subject, predicate=predicate, initial=initial, drain_timeout=drain_timeout
        )

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

    async def serve_mcp(self, *, default_mcp: bool = True) -> None:
        """Serve mesh agents to an MCP client over stdio (ADR-0002).

        Requires the ``mcp`` extra: ``pip install 'openagentmesh[mcp]'``.
        """
        from ._mcp import serve_mcp

        await serve_mcp(self, default_mcp=default_mcp)

    def run_mcp(self, *, default_mcp: bool = True) -> None:
        """Block serving MCP over stdio. Like ``run()``, for MCP clients::

            mesh = AgentMesh()

            @mesh.agent(spec, mcp=True)
            async def summarize(req: In) -> Out: ...

            mesh.run_mcp(default_mcp=False)  # opt-in export
        """
        with suppress(KeyboardInterrupt):
            asyncio.run(self.serve_mcp(default_mcp=default_mcp))

    # --- Agent subscription ---

    async def _subscribe_agent(
        self, name: str, info: HandlerInfo, contract: AgentContract
    ) -> None:
        subject = contract.subject
        queue = f"q.{name}"

        async def handler(msg: Msg) -> None:
            request_id = ""
            wants_stream = False
            if msg.headers:
                request_id = msg.headers.get("X-Mesh-Request-Id", "")
                wants_stream = msg.headers.get("X-Mesh-Stream") == "true"

            started = time.monotonic()
            await self._publish_log(
                name, "debug", "request_received", request_id=request_id
            )
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

                duration_ms = int((time.monotonic() - started) * 1000)
                await self._publish_log(
                    name, "debug", "request_completed",
                    request_id=request_id,
                    message=f"Request completed in {duration_ms}ms",
                    data={"duration_ms": duration_ms},
                )
            except MeshError as e:
                error = e
                log_event = (
                    "validation_error" if isinstance(e, InvalidInput) else "request_failed"
                )
                await self._publish_log(
                    name, "warn", log_event,
                    request_id=request_id,
                    message=e.message,
                    data={"code": e.code},
                )
                if wants_stream:
                    stream_subject = f"mesh.stream.{request_id}"
                    await self._conn.publish(
                        stream_subject,
                        error.to_json(),
                        headers=self._with_instance_id({
                            "X-Mesh-Stream-End": "true",
                            "X-Mesh-Status": "error",
                            "X-Mesh-Request-Id": request_id,
                        }),
                    )
                elif msg.reply:
                    await self._conn.publish(
                        msg.reply,
                        error.to_json(),
                        headers=self._with_instance_id({
                            "X-Mesh-Status": "error",
                            "X-Mesh-Request-Id": request_id,
                        }),
                    )
                await self._conn.publish(
                    compute_error_subject(name),
                    error.to_json(),
                    headers=self._with_instance_id({
                        "X-Mesh-Status": "error",
                        "X-Mesh-Request-Id": request_id,
                    }),
                )

        if name in self._agent_gates:
            # Gated agents (ADR-0055) run each request as a tracked task so
            # deactivation can unsubscribe instantly and drain the in-flight
            # set on its own timeout.
            inflight = self._inflight_tasks.setdefault(name, set())

            async def dispatch(msg: Msg) -> None:
                task = asyncio.create_task(handler(msg))
                inflight.add(task)
                task.add_done_callback(inflight.discard)

            cb = dispatch
        else:
            cb = handler

        sub = await self._conn.subscribe(subject, queue=queue, cb=cb)
        self._subscriptions[name] = sub

    async def _handle_responder(
        self,
        msg: Msg,
        info: HandlerInfo,
        agent_name: str,
        request_id: str,
        payload: Any,
    ) -> None:
        usage_token = begin_usage_capture()
        try:
            if payload is not None:
                result = await info.func(payload)
            else:
                result = await info.func()
        finally:
            usage = end_usage_capture(usage_token)

        if info.output_adapter and result is not None:
            response_data = info.output_adapter.dump_json(result)
        else:
            response_data = json.dumps(result).encode() if result is not None else b"{}"

        if msg.reply:
            headers = {
                "X-Mesh-Status": "ok",
                "X-Mesh-Source": agent_name,
                "X-Mesh-Request-Id": request_id,
            }
            if usage is not None:
                headers[X_MESH_USAGE] = usage.model_dump_json(exclude_none=True)
            await self._conn.publish(
                msg.reply,
                response_data,
                headers=self._with_instance_id(headers),
            )
        await self._publish_usage(agent_name, request_id, usage)

    async def _handle_streaming(
        self,
        msg: Msg,
        info: HandlerInfo,
        agent_name: str,
        request_id: str,
        payload: Any,
    ) -> None:
        stream_subject = f"mesh.stream.{request_id}"

        usage_token = begin_usage_capture()
        try:
            gen = info.func(payload) if payload is not None else info.func()
            seq = 0
            async for chunk in gen:
                if info.output_adapter:
                    chunk_data = info.output_adapter.dump_json(chunk)
                else:
                    chunk_data = json.dumps(chunk).encode()

                await self._conn.publish(
                    stream_subject,
                    chunk_data,
                    headers=self._with_instance_id({
                        "X-Mesh-Stream-Seq": str(seq),
                        "X-Mesh-Stream-End": "false",
                        "X-Mesh-Request-Id": request_id,
                    }),
                )
                await self._conn.flush()
                seq += 1
        finally:
            usage = end_usage_capture(usage_token)

        # Usage rides the end frame: it is only known once the generator
        # finishes, and the end frame is the one message every consumer
        # reads to completion (ADR-0023).
        end_headers = {
            "X-Mesh-Stream-Seq": str(seq),
            "X-Mesh-Stream-End": "true",
            "X-Mesh-Request-Id": request_id,
        }
        if usage is not None:
            end_headers[X_MESH_USAGE] = usage.model_dump_json(exclude_none=True)
        await self._conn.publish(
            stream_subject,
            b"",
            headers=self._with_instance_id(end_headers),
        )
        await self._conn.flush()
        await self._publish_usage(agent_name, request_id, usage)

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

                await self._conn.publish(
                    event_subject,
                    data,
                    headers=self._with_instance_id({
                        "X-Mesh-Stream-Seq": str(seq),
                        "X-Mesh-Stream-End": "false",
                    }),
                )
                seq += 1

            await self._conn.publish(
                event_subject,
                b"",
                headers=self._with_instance_id({
                    "X-Mesh-Stream-Seq": str(seq),
                    "X-Mesh-Stream-End": "true",
                }),
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await self._conn.publish(
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
                await self._conn.publish(
                    event_subject,
                    error.to_json(),
                    headers=self._with_instance_id({
                        "X-Mesh-Stream-End": "true",
                        "X-Mesh-Status": "error",
                    }),
                )
                await self._conn.publish(
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

        sub = await self._conn.subscribe(
            source.subject,
            queue=source.queue_group,
            cb=cb,
        )
        self._source_subscriptions.setdefault(name, []).append(sub)

    async def _bind_kv_source(self, name: str, info: HandlerInfo, source: Any) -> None:
        assert self._context_kv is not None
        watcher = await self._context_kv.watch(source.pattern)
        task = asyncio.create_task(
            self._drain_kv_source(name, info, source, watcher)
        )
        self._source_tasks.setdefault(name, []).append(task)

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
                operation="DELETE" if kv_operation == "DELETE" else "PUT",
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

    # --- Liveness helpers (ADR-0016) ---

    async def _agents_served_by_live_instances(self) -> set[str]:
        """Union of agent names across all current mesh-instances records."""
        served: set[str] = set()
        if self._instances_kv is None:
            return served
        try:
            keys = await self._instances_kv.keys()
        except Exception:
            return served  # empty bucket raises NoKeysError
        for key in keys:
            try:
                entry = await self._instances_kv.get(key)
                served.update(json.loads(entry.value or b"{}").get("agents", []))
            except Exception:
                continue
        return served

    async def _deregister_agent_record(self, name: str) -> None:
        """Remove an agent from the catalog and registry."""
        assert self._registry_kv is not None
        await self._catalog_cas(name, None)
        with suppress(Exception):
            await self._registry_kv.delete(name)

    async def _update_catalog(self, contract: AgentContract, *, add: bool) -> None:
        entry_dict = contract.to_catalog_entry().model_dump() if add else None
        await self._catalog_cas(contract.name, entry_dict)

    async def _catalog_cas(self, name: str, entry_dict: dict | None) -> None:
        """CAS-update the catalog: replace `name`'s entry, or remove it when
        `entry_dict` is None."""
        assert self._catalog_kv is not None

        from nats.js.errors import KeyNotFoundError

        for _ in range(10):
            try:
                kv_entry = await self._catalog_kv.get(_CATALOG_KEY)
                current: list[dict] = json.loads(kv_entry.value or b"[]")
                revision = kv_entry.revision or 0
            except (KeyNotFoundError, Exception):
                current = []
                revision = 0

            current = [e for e in current if e.get("name") != name]
            if entry_dict is not None:
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
