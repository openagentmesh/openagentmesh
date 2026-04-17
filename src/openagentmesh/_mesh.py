"""AgentMesh: the main entry point for the OpenAgentMesh SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import nats
from nats.aio.client import Client as NatsClient
from nats.js import JetStreamContext
from nats.js.kv import KeyValue
from pydantic import BaseModel

from ._context import ContextStore
from ._handler import HandlerInfo, inspect_handler
from ._local import EmbeddedNats
from ._models import (
    AgentContract,
    AgentSpec,
    BufferedNotSupported,
    CatalogEntry,
    ChunkSequenceError,
    MeshError,
    MeshTimeout,
    StreamingNotSupported,
)

_log = logging.getLogger("openagentmesh")

_CATALOG_BUCKET = "mesh-catalog"
_REGISTRY_BUCKET = "mesh-registry"
_CONTEXT_BUCKET = "mesh-context"
_CATALOG_KEY = "catalog"


def _compute_subject(name: str, channel: str | None) -> str:
    if channel:
        return f"mesh.agent.{channel}.{name}"
    return f"mesh.agent.{name}"


def _compute_registry_key(name: str, channel: str | None) -> str:
    if channel:
        return f"{channel}.{name}"
    return name


class AgentMesh:
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
        self._nc: NatsClient | None = None
        self._js: JetStreamContext | None = None
        self._catalog_kv: KeyValue | None = None
        self._registry_kv: KeyValue | None = None
        self._context_kv: KeyValue | None = None
        self.kv: ContextStore | None = None

        # Registered agents and subscription tracking
        self._agents: dict[str, tuple[AgentSpec, HandlerInfo, AgentContract]] = {}
        self._subscribed: set[str] = set()
        self._subscriptions: list[Any] = []
        self._embedded: EmbeddedNats | None = None
        self._catalog_cache: dict[str, CatalogEntry] = {}
        self._catalog_watcher_task: asyncio.Task | None = None
        self._publisher_tasks: dict[str, asyncio.Task] = {}

    # --- Async context manager ---

    async def __aenter__(self) -> AgentMesh:
        await self._connect()
        await self._ensure_buckets()
        self._start_catalog_watcher()
        await self._subscribe_pending()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._shutdown()

    # --- Connection (private) ---

    async def _connect(self) -> None:
        if self._nc is not None:
            return
        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()

    async def _ensure_buckets(self) -> None:
        assert self._js is not None
        try:
            self._catalog_kv = await self._js.key_value(_CATALOG_BUCKET)
        except Exception:
            self._catalog_kv = await self._js.create_key_value(bucket=_CATALOG_BUCKET)

        try:
            self._registry_kv = await self._js.key_value(_REGISTRY_BUCKET)
        except Exception:
            self._registry_kv = await self._js.create_key_value(bucket=_REGISTRY_BUCKET)

        try:
            self._context_kv = await self._js.key_value(_CONTEXT_BUCKET)
        except Exception:
            self._context_kv = await self._js.create_key_value(bucket=_CONTEXT_BUCKET)

        self.kv = ContextStore(self._context_kv)

    async def _subscribe_pending(self) -> None:
        """Subscribe any agents not yet subscribed."""
        for name, (spec, info, contract) in self._agents.items():
            if name not in self._subscribed:
                if info.invocable:
                    await self._subscribe_agent(name, info, contract)
                else:
                    # Publisher agent: launch emission task (ADR-0034)
                    if name not in self._publisher_tasks:
                        task = asyncio.create_task(
                            self._emit_publisher_events(name, spec, info)
                        )
                        self._publisher_tasks[name] = task
                await self._publish_contract(contract)
                await self._update_catalog(contract, add=True)
                self._catalog_cache[name] = contract.to_catalog_entry()
                self._subscribed.add(name)

    def _start_catalog_watcher(self) -> None:
        """Start background task that watches the catalog KV for changes (ADR-0032)."""
        assert self._catalog_kv is not None

        async def _watch() -> None:
            try:
                watcher = await self._catalog_kv.watchall()
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
                pass
            except Exception:
                pass

        self._catalog_watcher_task = asyncio.create_task(_watch())

    async def _shutdown(self) -> None:
        if self._catalog_watcher_task is not None:
            self._catalog_watcher_task.cancel()
            try:
                await self._catalog_watcher_task
            except (asyncio.CancelledError, Exception):
                pass
            self._catalog_watcher_task = None

        # Cancel publisher tasks (ADR-0034)
        for task in self._publisher_tasks.values():
            task.cancel()
        for task in self._publisher_tasks.values():
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._publisher_tasks.clear()

        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        self._subscriptions.clear()

        if self._catalog_kv and self._registry_kv:
            for name in self._subscribed:
                if name in self._agents:
                    spec, _, contract = self._agents[name]
                    try:
                        await self._update_catalog(contract, add=False)
                    except Exception:
                        pass
                    try:
                        key = _compute_registry_key(name, spec.channel)
                        await self._registry_kv.delete(key)
                    except Exception:
                        pass

        self._subscribed.clear()

        if self._nc and self._nc.is_connected:
            try:
                await self._nc.drain()
            except Exception:
                try:
                    await self._nc.close()
                except Exception:
                    pass
            self._nc = None

    # --- local() ---

    @classmethod
    @asynccontextmanager
    async def local(cls) -> AsyncIterator[AgentMesh]:
        """Embedded NATS for tests and demos.

        Starts a NATS subprocess, connects, creates KV buckets,
        and tears everything down on exit::

            async with AgentMesh.local() as mesh:
                @mesh.agent(spec)
                async def echo(req: EchoInput) -> EchoOutput:
                    ...
                result = await mesh.call("echo", {"message": "hi"})
        """
        embedded = EmbeddedNats()
        await embedded.start()
        mesh = cls(url=embedded.url)
        mesh._embedded = embedded
        try:
            async with mesh:
                yield mesh
        finally:
            await embedded.stop()

    # --- Registration ---

    def agent(self, spec: AgentSpec):
        """Decorator to register an async function as a mesh agent.

        Usage::

            spec = AgentSpec(name="echo", description="Echoes messages")

            @mesh.agent(spec)
            async def echo(req: EchoInput) -> EchoOutput:
                return EchoOutput(reply=f"Echo: {req.message}")
        """

        def decorator(func):
            info = inspect_handler(func)

            subject = _compute_subject(spec.name, spec.channel)
            contract = AgentContract(
                name=spec.name,
                description=spec.description,
                version=spec.version,
                channel=spec.channel,
                subject=subject,
                tags=spec.tags,
                invocable=info.invocable,
                streaming=info.streaming,
                capabilities={"streaming": info.streaming, "invocable": info.invocable},
                input_schema=(
                    info.input_model.model_json_schema() if info.input_model else None
                ),
                output_schema=(
                    info.output_model.model_json_schema() if info.output_model else None
                ),
                chunk_schema=(
                    info.output_model.model_json_schema()
                    if info.streaming and info.output_model
                    else None
                ),
            )
            if info.streaming:
                contract.output_schema = None

            self._agents[spec.name] = (spec, info, contract)
            return func

        return decorator

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
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass

        try:
            asyncio.run(_run_forever())
        except KeyboardInterrupt:
            pass

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
                # Defense-in-depth capability enforcement (ADR-0005)
                if wants_stream and not info.streaming:
                    raise StreamingNotSupported(agent=name, request_id=request_id)
                if not wants_stream and info.streaming:
                    raise BufferedNotSupported(agent=name, request_id=request_id)

                if info.streaming:
                    await self._handle_streaming(msg, info, name, request_id)
                else:
                    await self._handle_buffered(msg, info, name, request_id)
            except Exception as e:
                error = (
                    e if isinstance(e, MeshError)
                    else MeshError(
                        code="handler_error", message=str(e),
                        agent=name, request_id=request_id,
                    )
                )
                if wants_stream:
                    stream_subject = f"mesh.stream.{request_id}"
                    await self._nc.publish(
                        stream_subject,
                        error.to_json(),
                        headers={
                            "X-Mesh-Stream-End": "true",
                            "X-Mesh-Status": "error",
                            "X-Mesh-Request-Id": request_id,
                        },
                    )
                elif msg.reply:
                    await self._nc.publish(
                        msg.reply,
                        error.to_json(),
                        headers={"X-Mesh-Status": "error", "X-Mesh-Request-Id": request_id},
                    )

        sub = await self._nc.subscribe(subject, queue=queue, cb=handler)
        self._subscriptions.append(sub)

    async def _handle_buffered(
        self,
        msg: nats.aio.msg.Msg,
        info: HandlerInfo,
        agent_name: str,
        request_id: str,
    ) -> None:
        if info.input_model and msg.data:
            payload = info.input_model.model_validate_json(msg.data)
        else:
            payload = None

        if payload is not None:
            result = await info.func(payload)
        else:
            result = await info.func()

        if isinstance(result, BaseModel):
            response_data = result.model_dump_json().encode()
        else:
            response_data = json.dumps(result).encode() if result is not None else b"{}"

        if msg.reply:
            await self._nc.publish(
                msg.reply,
                response_data,
                headers={
                    "X-Mesh-Status": "ok",
                    "X-Mesh-Source": agent_name,
                    "X-Mesh-Request-Id": request_id,
                },
            )

    async def _handle_streaming(
        self,
        msg: nats.aio.msg.Msg,
        info: HandlerInfo,
        agent_name: str,
        request_id: str,
    ) -> None:
        stream_subject = f"mesh.stream.{request_id}"

        if info.input_model and msg.data:
            payload = info.input_model.model_validate_json(msg.data)
        else:
            payload = None

        gen = info.func(payload) if payload is not None else info.func()
        seq = 0
        async for chunk in gen:
            if isinstance(chunk, BaseModel):
                chunk_data = chunk.model_dump_json().encode()
            else:
                chunk_data = json.dumps(chunk).encode()

            await self._nc.publish(
                stream_subject,
                chunk_data,
                headers={
                    "X-Mesh-Stream-Seq": str(seq),
                    "X-Mesh-Stream-End": "false",
                    "X-Mesh-Request-Id": request_id,
                },
            )
            seq += 1

        await self._nc.publish(
            stream_subject,
            b"",
            headers={
                "X-Mesh-Stream-Seq": str(seq),
                "X-Mesh-Stream-End": "true",
                "X-Mesh-Request-Id": request_id,
            },
        )

    # --- Publisher emission (ADR-0034) ---

    async def _emit_publisher_events(
        self, name: str, spec: AgentSpec, info: HandlerInfo
    ) -> None:
        """Run a publisher handler and publish yielded values to its event subject."""
        if spec.channel:
            event_subject = f"mesh.agent.{spec.channel}.{name}.events"
        else:
            event_subject = f"mesh.agent.{name}.events"

        gen = info.func()
        seq = 0
        try:
            async for chunk in gen:
                if isinstance(chunk, BaseModel):
                    data = chunk.model_dump_json().encode()
                else:
                    data = json.dumps(chunk).encode()

                await self._nc.publish(
                    event_subject,
                    data,
                    headers={
                        "X-Mesh-Stream-Seq": str(seq),
                        "X-Mesh-Stream-End": "false",
                    },
                )
                seq += 1

            # Generator returned normally: send terminal
            await self._nc.publish(
                event_subject,
                b"",
                headers={
                    "X-Mesh-Stream-Seq": str(seq),
                    "X-Mesh-Stream-End": "true",
                },
            )
        except asyncio.CancelledError:
            # Shutdown: send terminal
            try:
                await self._nc.publish(
                    event_subject,
                    b"",
                    headers={
                        "X-Mesh-Stream-Seq": str(seq),
                        "X-Mesh-Stream-End": "true",
                    },
                )
            except Exception:
                pass
        except Exception as e:
            _log.warning("Publisher '%s' failed: %s", name, e)
            error = MeshError(
                code="handler_error", message=str(e), agent=name,
            )
            try:
                await self._nc.publish(
                    event_subject,
                    error.to_json(),
                    headers={
                        "X-Mesh-Stream-End": "true",
                        "X-Mesh-Status": "error",
                    },
                )
            except Exception:
                pass

    # --- Invocation ---

    async def call(self, name: str, payload: Any = None, timeout: float = 30.0) -> dict:
        """Synchronous request/reply. Returns the response as a dict."""
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."
        await self._subscribe_pending()
        self._check_buffered(name)

        subject = self._resolve_subject(name)
        request_id = uuid.uuid4().hex
        data = self._serialize_payload(payload)

        response = await self._nc.request(
            subject, data, timeout=timeout,
            headers={"X-Mesh-Request-Id": request_id},
        )

        status = ""
        if response.headers:
            status = response.headers.get("X-Mesh-Status", "")

        if status == "error":
            err = json.loads(response.data)
            raise MeshError(
                code=err.get("code", "unknown"),
                message=err.get("message", "Unknown error"),
                agent=err.get("agent", name),
                request_id=request_id,
                details=err.get("details", {}),
            )

        return json.loads(response.data) if response.data else {}

    async def stream(
        self, name: str, payload: Any = None, timeout: float = 60.0
    ) -> AsyncIterator[dict]:
        """Streaming request. Yields response chunks as dicts."""
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."
        await self._subscribe_pending()
        self._check_streaming(name)

        subject = self._resolve_subject(name)
        request_id = uuid.uuid4().hex
        stream_subject = f"mesh.stream.{request_id}"

        chunks: asyncio.Queue[dict | MeshError | None] = asyncio.Queue()
        expected_seq = [0]

        async def chunk_handler(msg: nats.aio.msg.Msg) -> None:
            is_end = msg.headers and msg.headers.get("X-Mesh-Stream-End") == "true"
            is_error = msg.headers and msg.headers.get("X-Mesh-Status") == "error"

            if is_error and msg.data:
                err = json.loads(msg.data)
                await chunks.put(MeshError(
                    code=err.get("code", "handler_error"),
                    message=err.get("message", "Unknown streaming error"),
                    agent=err.get("agent", name),
                    request_id=request_id,
                    details=err.get("details", {}),
                ))
                return

            if is_end:
                await chunks.put(None)
                return

            if msg.data and msg.headers:
                seq = int(msg.headers.get("X-Mesh-Stream-Seq", "-1"))
                if seq != expected_seq[0]:
                    await chunks.put(ChunkSequenceError(
                        agent=name,
                        request_id=request_id,
                        details={"expected_seq": expected_seq[0], "got_seq": seq},
                    ))
                    return
                expected_seq[0] += 1
                await chunks.put(json.loads(msg.data))

        sub = await self._nc.subscribe(stream_subject, cb=chunk_handler)

        try:
            data = self._serialize_payload(payload)
            headers = {
                "X-Mesh-Request-Id": request_id,
                "X-Mesh-Stream": "true",
            }
            await self._nc.publish(subject, data, headers=headers)

            deadline = asyncio.get_event_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise MeshError(
                        code="timeout", message="Stream timed out", agent=name
                    )
                chunk = await asyncio.wait_for(chunks.get(), timeout=remaining)
                if chunk is None:
                    break
                if isinstance(chunk, MeshError):
                    raise chunk
                yield chunk
        finally:
            await sub.unsubscribe()

    async def subscribe(
        self,
        *,
        agent: str | None = None,
        channel: str | None = None,
        subject: str | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[dict]:
        """Subscribe to events on a subject, agent, or channel.

        Yields dicts parsed from incoming JSON messages. The generator
        terminates when a message with ``X-Mesh-Stream-End: true`` arrives,
        or when the caller breaks out of the loop.

        At least one of *agent*, *channel*, or *subject* must be provided.
        *agent* and *subject* are mutually exclusive. *channel* can be
        combined with *agent* to override the agent's registered channel.
        """
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."

        # --- parameter validation ---
        if agent is not None and subject is not None:
            raise ValueError("'agent' and 'subject' are mutually exclusive")
        if agent is None and channel is None and subject is None:
            raise ValueError("Provide 'agent', 'channel', or 'subject'")

        # --- resolve target subject ---
        if subject:
            resolved = subject
        elif agent:
            resolved = self._resolve_event_subject(agent, channel)
        else:
            # channel only
            resolved = f"mesh.agent.{channel}.>"

        # --- queue-based async generator ---
        items: asyncio.Queue[dict | MeshError | None] = asyncio.Queue()

        async def _on_msg(msg: nats.aio.msg.Msg) -> None:
            is_end = msg.headers and msg.headers.get("X-Mesh-Stream-End") == "true"
            is_error = msg.headers and msg.headers.get("X-Mesh-Status") == "error"

            if is_error and msg.data:
                err = json.loads(msg.data)
                await items.put(MeshError(
                    code=err.get("code", "unknown"),
                    message=err.get("message", "Unknown error"),
                    agent=err.get("agent", ""),
                    request_id=err.get("request_id", ""),
                    details=err.get("details", {}),
                ))
                return

            if msg.data:
                await items.put(json.loads(msg.data))

            if is_end:
                await items.put(None)

        # Subscribe to NATS *before* launching publisher tasks so the
        # subscriber is ready to receive the first emitted event.
        sub = await self._nc.subscribe(resolved, cb=_on_msg)
        await self._subscribe_pending()

        try:
            while True:
                if timeout is not None:
                    try:
                        item = await asyncio.wait_for(items.get(), timeout=timeout)
                    except asyncio.TimeoutError:
                        raise MeshTimeout(subject=resolved, timeout=timeout)
                else:
                    item = await items.get()

                if item is None:
                    break
                if isinstance(item, MeshError):
                    raise item
                yield item
        finally:
            await sub.unsubscribe()

    async def send(
        self, name: str, payload: Any = None, reply_to: str | None = None
    ) -> None:
        """Fire-and-forget invocation with optional reply subject."""
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."
        await self._subscribe_pending()

        subject = self._resolve_subject(name)
        request_id = uuid.uuid4().hex
        data = self._serialize_payload(payload)

        headers: dict[str, str] = {"X-Mesh-Request-Id": request_id}
        if reply_to:
            headers["X-Mesh-Reply-To"] = reply_to

        await self._nc.publish(subject, data, headers=headers, reply=reply_to or "")

    # --- Discovery ---

    async def catalog(
        self,
        channel: str | None = None,
        tags: list[str] | None = None,
        streaming: bool | None = None,
        invocable: bool | None = None,
    ) -> list[CatalogEntry]:
        """Lightweight agent listing from the catalog cache (ADR-0028, ADR-0032)."""
        await self._subscribe_pending()

        entries = list(self._catalog_cache.values())

        if channel is not None:
            entries = [e for e in entries if e.channel == channel]
        if tags is not None:
            tag_set = set(tags)
            entries = [e for e in entries if tag_set.issubset(set(e.tags))]
        if streaming is not None:
            entries = [e for e in entries if e.streaming == streaming]
        if invocable is not None:
            entries = [e for e in entries if e.invocable == invocable]

        return entries

    async def contract(self, name: str, channel: str | None = None) -> AgentContract:
        """Fetch full contract from the registry (authoritative)."""
        assert self._registry_kv is not None

        key = _compute_registry_key(name, channel)

        if channel is None and name in self._agents:
            _, _, c = self._agents[name]
            return c

        try:
            entry = await self._registry_kv.get(key)
        except Exception:
            if channel is not None:
                try:
                    entry = await self._registry_kv.get(name)
                except Exception:
                    raise MeshError(code="not_found", message=f"Agent '{name}' not found")
            else:
                raise MeshError(code="not_found", message=f"Agent '{name}' not found")

        data = json.loads(entry.value)
        xam = data.get("x-agentmesh", {})
        caps = data.get("capabilities", {})

        return AgentContract(
            name=data["name"],
            description=data["description"],
            version=data.get("version", "0.1.0"),
            capabilities=caps,
            skills=data.get("skills", []),
            channel=xam.get("channel"),
            subject=xam.get("subject", ""),
            tags=xam.get("tags", []),
            invocable=caps.get("invocable", True),
            streaming=caps.get("streaming", False),
            chunk_schema=xam.get("chunk_schema"),
        )

    async def discover(self, channel: str | None = None) -> list[AgentContract]:
        """Full contract listing. Heavier than catalog(), authoritative."""
        catalog_entries = await self.catalog(channel=channel)
        contracts = []
        for entry in catalog_entries:
            try:
                c = await self.contract(entry.name, channel=entry.channel)
                contracts.append(c)
            except MeshError:
                continue
        return contracts

    # --- Capability checks (ADR-0005) ---

    def _check_streaming(self, name: str) -> None:
        """Raise StreamingNotSupported if agent does not stream."""
        if name in self._agents:
            _, _, contract = self._agents[name]
            if not contract.streaming:
                raise StreamingNotSupported(agent=name)
            return
        entry = self._catalog_cache.get(name)
        if entry is not None and not entry.streaming:
            raise StreamingNotSupported(agent=name)

    def _check_buffered(self, name: str) -> None:
        """Raise BufferedNotSupported if agent is streaming-only."""
        if name in self._agents:
            _, _, contract = self._agents[name]
            if contract.streaming:
                raise BufferedNotSupported(agent=name)
            return
        entry = self._catalog_cache.get(name)
        if entry is not None and entry.streaming:
            raise BufferedNotSupported(agent=name)

    # --- Internal helpers ---

    def _resolve_subject(self, name: str) -> str:
        if name in self._agents:
            _, _, contract = self._agents[name]
            return contract.subject
        return f"mesh.agent.{name}"

    def _resolve_event_subject(self, name: str, channel: str | None = None) -> str:
        """Resolve an agent name to its event subject."""
        if name in self._agents:
            spec, _, _ = self._agents[name]
            ch = channel or spec.channel
            if ch:
                return f"mesh.agent.{ch}.{name}.events"
            return f"mesh.agent.{name}.events"

        entry = self._catalog_cache.get(name)
        if entry is not None:
            ch = channel or entry.channel
            if ch:
                return f"mesh.agent.{ch}.{name}.events"
            return f"mesh.agent.{name}.events"

        raise MeshError(code="not_found", message=f"Agent '{name}' not found")

    @staticmethod
    def _serialize_payload(payload: Any) -> bytes:
        if payload is None:
            return b""
        if isinstance(payload, BaseModel):
            return payload.model_dump_json().encode()
        if isinstance(payload, dict):
            return json.dumps(payload).encode()
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload.encode()
        return json.dumps(payload).encode()

    async def _publish_contract(self, contract: AgentContract) -> None:
        assert self._registry_kv is not None
        key = _compute_registry_key(contract.name, contract.channel)
        await self._registry_kv.put(key, contract.to_registry_json().encode())

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
