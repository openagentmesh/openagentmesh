"""Invocation primitives: call, stream, subscribe, send."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator, TYPE_CHECKING

import nats

from ._models import ChunkSequenceError, MeshError, MeshTimeout

if TYPE_CHECKING:
    from ._mesh import AgentMesh

_log = logging.getLogger("openagentmesh")


class InvocationMixin:

    async def call(self: AgentMesh, name: str, payload: Any = None, timeout: float = 30.0) -> dict:
        """Synchronous request/reply. Returns the response as a dict."""
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."
        await self._subscribe_pending()
        self._check_capability(name, "call")

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
        self: AgentMesh, name: str, payload: Any = None, timeout: float = 60.0
    ) -> AsyncIterator[dict]:
        """Streaming request. Yields response chunks as dicts."""
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."
        await self._subscribe_pending()
        self._check_capability(name, "stream")

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
        self: AgentMesh,
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
        *agent* and *subject* are mutually exclusive. *channel* subscribes
        to every agent whose name starts with that prefix (ADR-0049).
        """
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."

        if agent is not None and subject is not None:
            raise ValueError("'agent' and 'subject' are mutually exclusive")
        if agent is None and channel is None and subject is None:
            raise ValueError("Provide 'agent', 'channel', or 'subject'")

        if agent:
            self._check_capability(agent, "subscribe")

        if subject:
            resolved = subject
        elif agent:
            resolved = await self._resolve_event_subject(agent)
        else:
            resolved = f"mesh.agent.{channel}.>"

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
        self: AgentMesh,
        name: str,
        payload: Any = None,
        *,
        on_reply: Any = None,
        on_error: Any = None,
        reply_to: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Fire-and-forget invocation with optional managed callback (ADR-0034).

        Three modes:

        - No ``on_reply``, no ``reply_to``: pure fire-and-forget.
        - ``reply_to="subject"``: legacy manual reply subject.
        - ``on_reply=callback``: SDK manages request ID, subscription, and cleanup.
          Optional ``on_error=callback`` fires on timeout or handler error.
        """
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."
        await self._subscribe_pending()
        self._check_capability(name, "send")

        if on_reply is not None and reply_to is not None:
            raise ValueError("'on_reply' and 'reply_to' are mutually exclusive")

        subject = self._resolve_subject(name)
        request_id = uuid.uuid4().hex
        data = self._serialize_payload(payload)

        if on_reply is not None:
            reply_subject = f"mesh.results.{request_id}"

            async def _callback_task() -> None:
                try:
                    async for msg in self.subscribe(subject=reply_subject, timeout=timeout):
                        await on_reply(msg)
                except MeshTimeout as e:
                    if on_error is not None:
                        await on_error(e)
                    else:
                        _log.warning("send('%s') reply timed out: %s", name, e)
                except MeshError as e:
                    if on_error is not None:
                        await on_error(e)
                    else:
                        _log.warning("send('%s') reply error: %s", name, e)

            asyncio.create_task(_callback_task())

            headers: dict[str, str] = {"X-Mesh-Request-Id": request_id}
            await self._nc.publish(subject, data, headers=headers, reply=reply_subject)
        else:
            headers = {"X-Mesh-Request-Id": request_id}
            if reply_to:
                headers["X-Mesh-Reply-To"] = reply_to
            await self._nc.publish(subject, data, headers=headers, reply=reply_to or "")
