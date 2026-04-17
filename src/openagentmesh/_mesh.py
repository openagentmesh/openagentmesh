"""AgentMesh: the main entry point for the OpenAgentMesh SDK."""

from __future__ import annotations

import asyncio
import inspect
import json
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
from ._models import AgentContract, AgentSpec, CatalogEntry, MeshError

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

    Constructors::

        mesh = AgentMesh()                           # localhost:4222
        mesh = AgentMesh("nats://mesh.example.com")  # explicit URL

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
        self.context: ContextStore | None = None

        # Registered agents (pending start)
        self._agents: dict[str, tuple[AgentSpec, HandlerInfo, AgentContract]] = {}
        self._subscriptions: list[Any] = []
        self._running = False
        self._embedded: EmbeddedNats | None = None

    # --- Connection ---

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

        self.context = ContextStore(self._context_kv)

    # --- local() context manager ---

    @classmethod
    @asynccontextmanager
    async def local(cls) -> AsyncIterator[AgentMesh]:
        """Async context manager: start an embedded NATS server for tests/demos.

        Usage::

            async with AgentMesh.local() as mesh:
                @mesh.agent(spec)
                async def echo(req: EchoInput) -> EchoOutput:
                    ...
                await mesh.start()
                result = await mesh.call("echo", ...)
        """
        embedded = EmbeddedNats()
        await embedded.start()
        mesh = cls(url=embedded.url)
        mesh._embedded = embedded
        try:
            await mesh._connect()
            await mesh._ensure_buckets()
            yield mesh
        finally:
            await mesh._shutdown()
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
                contract.output_schema = None  # streaming agents use chunk_schema

            self._agents[spec.name] = (spec, info, contract)
            return func

        return decorator

    # --- Lifecycle ---

    async def start(self) -> None:
        """Connect (if needed), subscribe agents, publish contracts."""
        await self._connect()
        await self._ensure_buckets()

        for name, (spec, info, contract) in self._agents.items():
            await self._subscribe_agent(name, info, contract)
            await self._publish_contract(contract)
            await self._update_catalog(contract, add=True)

        self._running = True

    async def stop(self) -> None:
        """Graceful shutdown: drain subscriptions, deregister, disconnect."""
        await self._shutdown()

    async def _shutdown(self) -> None:
        self._running = False

        # Drain subscriptions
        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        self._subscriptions.clear()

        # Deregister from catalog and registry
        if self._catalog_kv and self._registry_kv:
            for name, (spec, _, contract) in self._agents.items():
                try:
                    await self._update_catalog(contract, add=False)
                except Exception:
                    pass
                try:
                    key = _compute_registry_key(name, spec.channel)
                    await self._registry_kv.delete(key)
                except Exception:
                    pass

        # Close NATS connection
        if self._nc and self._nc.is_connected:
            try:
                await self._nc.drain()
            except Exception:
                try:
                    await self._nc.close()
                except Exception:
                    pass
            self._nc = None

    def run(self) -> None:
        """Start the mesh and block until interrupted. Like ``uvicorn.run()``."""

        async def _run_forever():
            await self.start()
            try:
                stop_event = asyncio.Event()
                await stop_event.wait()
            except asyncio.CancelledError:
                pass
            finally:
                await self.stop()

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
            if msg.headers:
                request_id = msg.headers.get("X-Mesh-Request-Id", "")

            try:
                if info.streaming:
                    await self._handle_streaming(msg, info, name, request_id)
                else:
                    await self._handle_buffered(msg, info, name, request_id)
            except Exception as e:
                error = MeshError(
                    code="handler_error", message=str(e), agent=name, request_id=request_id
                )
                if msg.reply:
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
        # Deserialize input
        if info.input_model and msg.data:
            payload = info.input_model.model_validate_json(msg.data)
        else:
            payload = None

        # Execute handler
        if payload is not None:
            result = await info.func(payload)
        else:
            result = await info.func()

        # Serialize output
        if isinstance(result, BaseModel):
            response_data = result.model_dump_json().encode()
        else:
            response_data = json.dumps(result).encode() if result is not None else b"{}"

        # Respond
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

        # Deserialize input
        if info.input_model and msg.data:
            payload = info.input_model.model_validate_json(msg.data)
        else:
            payload = None

        # Execute async generator
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

        # End-of-stream marker
        await self._nc.publish(
            stream_subject,
            b"",
            headers={
                "X-Mesh-Stream-Seq": str(seq),
                "X-Mesh-Stream-End": "true",
                "X-Mesh-Request-Id": request_id,
            },
        )

    # --- Invocation ---

    async def call(self, name: str, payload: Any = None, timeout: float = 30.0) -> dict:
        """Synchronous request/reply invocation.

        Returns the response as a dict.
        """
        assert self._nc is not None, "Not connected. Call start() first."

        subject = self._resolve_subject(name)
        request_id = uuid.uuid4().hex
        data = self._serialize_payload(payload)

        headers = {
            "X-Mesh-Request-Id": request_id,
        }

        response = await self._nc.request(
            subject, data, timeout=timeout, headers=headers
        )

        # Check status
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
        """Streaming request: yields response chunks as dicts."""
        assert self._nc is not None, "Not connected. Call start() first."

        subject = self._resolve_subject(name)
        request_id = uuid.uuid4().hex
        stream_subject = f"mesh.stream.{request_id}"

        # Subscribe to stream subject before sending request
        chunks: asyncio.Queue[dict | None] = asyncio.Queue()

        async def chunk_handler(msg: nats.aio.msg.Msg) -> None:
            is_end = msg.headers and msg.headers.get("X-Mesh-Stream-End") == "true"
            if is_end:
                await chunks.put(None)
            elif msg.data:
                await chunks.put(json.loads(msg.data))

        sub = await self._nc.subscribe(stream_subject, cb=chunk_handler)

        try:
            data = self._serialize_payload(payload)
            headers = {
                "X-Mesh-Request-Id": request_id,
                "X-Mesh-Stream": "true",
            }
            await self._nc.publish(subject, data, headers=headers)

            # Yield chunks until end marker
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
                yield chunk
        finally:
            await sub.unsubscribe()

    async def send(
        self, name: str, payload: Any = None, reply_to: str | None = None
    ) -> None:
        """Fire-and-forget invocation with optional reply subject."""
        assert self._nc is not None, "Not connected. Call start() first."

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
        """Lightweight agent listing from the catalog KV (ADR-0028)."""
        assert self._catalog_kv is not None

        try:
            entry = await self._catalog_kv.get(_CATALOG_KEY)
            entries = [CatalogEntry.model_validate(e) for e in json.loads(entry.value)]
        except Exception:
            return []

        # Filter
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

        # If channel not provided, try local registry first, then scan
        if channel is None and name in self._agents:
            _, _, c = self._agents[name]
            return c

        try:
            entry = await self._registry_kv.get(key)
        except Exception:
            # Try without channel
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

    # --- Internal helpers ---

    def _resolve_subject(self, name: str) -> str:
        """Resolve agent name to NATS subject."""
        if name in self._agents:
            _, _, contract = self._agents[name]
            return contract.subject

        # TODO: look up catalog for remote agents
        return f"mesh.agent.{name}"

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

    # --- Contract / catalog management ---

    async def _publish_contract(self, contract: AgentContract) -> None:
        assert self._registry_kv is not None
        key = _compute_registry_key(contract.name, contract.channel)
        await self._registry_kv.put(key, contract.to_registry_json().encode())

    async def _update_catalog(self, contract: AgentContract, *, add: bool) -> None:
        """CAS update the catalog: add or remove an entry."""
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

            # Remove existing entry with same name
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
