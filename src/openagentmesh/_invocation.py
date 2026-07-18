"""Invocation primitives: call, stream, subscribe, send, publish."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import nats.errors
from nats.aio.msg import Msg
from pydantic import BaseModel

from ._errors import (
    AgentDied,
    ChunkSequenceError,
    ConnectionDenied,
    MeshError,
    MeshTimeout,
    NotAvailable,
    NotFound,
    from_envelope,
)
from ._subjects import compute_death_subject

if TYPE_CHECKING:
    from ._mesh import AgentMesh

_log = logging.getLogger("openagentmesh")

# NATS subjects: dot-separated alphanumeric segments. No wildcards in publish.
_VALID_PUBLISH_SUBJECT = re.compile(r"^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)*$")

X_MESH_REQUEST_ID = "X-Mesh-Request-Id"
X_MESH_CONTENT_TYPE = "X-Mesh-Content-Type"


class InvocationMixin:

    async def call(self: AgentMesh, name: str, payload: Any = None, timeout: float = 30.0) -> dict:
        """Synchronous request/reply. Returns the response as a dict."""
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."
        await self._subscribe_pending()
        self._check_capability(name, "call")

        subject = self._resolve_subject(name)
        request_id = uuid.uuid4().hex
        data = self._serialize_payload(payload)

        # Race the request against a death notice for the target (ADR-0040):
        # if the agent leaves the mesh mid-request, fail sub-second instead
        # of waiting out the timeout.
        death_fut: asyncio.Future[dict] = asyncio.get_running_loop().create_future()

        async def _on_death(msg: Msg) -> None:
            if not death_fut.done():
                try:
                    death_fut.set_result(json.loads(msg.data) if msg.data else {})
                except Exception:
                    death_fut.set_result({})

        death_sub = await self._conn.subscribe(compute_death_subject(name), cb=_on_death)
        req_task = asyncio.ensure_future(
            self._conn.request(
                subject, data, timeout=timeout,
                headers=self._with_instance_id({"X-Mesh-Request-Id": request_id}),
            )
        )
        try:
            await asyncio.wait(
                {req_task, death_fut}, return_when=asyncio.FIRST_COMPLETED
            )
            if death_fut.done() and not req_task.done():
                req_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await req_task
                notice = death_fut.result()
                raise AgentDied(
                    message=f"Agent '{name}' left the mesh during the request",
                    agent=name,
                    request_id=request_id,
                    details=notice,
                )
            try:
                response = await req_task
            except nats.errors.NoRespondersError as e:
                # ADR-0055: an agent still in the catalog with no responders
                # is gated offline (or draining), not missing.
                if name in self._catalog_cache:
                    raise NotAvailable(agent=name, request_id=request_id) from e
                raise NotFound(agent=name, request_id=request_id) from e
            except nats.errors.TimeoutError as e:
                if subject.lower() in self._denied_subjects:
                    raise ConnectionDenied(
                        message=(
                            f"The server denied publishing to '{subject}': this "
                            "connection's credentials lack permission to invoke "
                            f"'{name}'"
                        ),
                        agent=name,
                        request_id=request_id,
                    ) from e
                raise MeshTimeout(subject=subject, timeout=timeout) from e
        finally:
            with contextlib.suppress(Exception):
                await death_sub.unsubscribe()

        status = ""
        if response.headers:
            status = response.headers.get("X-Mesh-Status", "")

        if status == "error":
            err = json.loads(response.data)
            envelope = {
                "code": err.get("code", "unknown"),
                "message": err.get("message", "Unknown error"),
                "agent": err.get("agent", name),
                "request_id": request_id,
                "details": err.get("details", {}),
            }
            raise from_envelope(envelope)

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

        async def chunk_handler(msg: Msg) -> None:
            is_end = msg.headers and msg.headers.get("X-Mesh-Stream-End") == "true"
            is_error = msg.headers and msg.headers.get("X-Mesh-Status") == "error"

            if is_error and msg.data:
                err = json.loads(msg.data)
                envelope = {
                    "code": err.get("code", "handler_error"),
                    "message": err.get("message", "Unknown streaming error"),
                    "agent": err.get("agent", name),
                    "request_id": request_id,
                    "details": err.get("details", {}),
                }
                await chunks.put(from_envelope(envelope))
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

        async def death_handler(msg: Msg) -> None:
            try:
                notice = json.loads(msg.data) if msg.data else {}
            except Exception:
                notice = {}
            await chunks.put(AgentDied(
                message=f"Agent '{name}' left the mesh mid-stream",
                agent=name,
                request_id=request_id,
                details=notice,
            ))

        sub = await self._conn.subscribe(stream_subject, cb=chunk_handler)
        # ADR-0040: the death listener stays active until the stream ends.
        death_sub = await self._conn.subscribe(
            compute_death_subject(name), cb=death_handler
        )

        try:
            data = self._serialize_payload(payload)
            headers = self._with_instance_id({
                "X-Mesh-Request-Id": request_id,
                "X-Mesh-Stream": "true",
            })
            await self._conn.publish(subject, data, headers=headers)

            deadline = asyncio.get_event_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise MeshTimeout(subject=stream_subject, timeout=timeout)
                chunk = await asyncio.wait_for(chunks.get(), timeout=remaining)
                if chunk is None:
                    break
                if isinstance(chunk, MeshError):
                    raise chunk
                yield chunk
        finally:
            with contextlib.suppress(Exception):
                await death_sub.unsubscribe()
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

        async def _on_msg(msg: Msg) -> None:
            is_end = msg.headers and msg.headers.get("X-Mesh-Stream-End") == "true"
            is_error = msg.headers and msg.headers.get("X-Mesh-Status") == "error"

            if is_error and msg.data:
                err = json.loads(msg.data)
                envelope = {
                    "code": err.get("code", "unknown"),
                    "message": err.get("message", "Unknown error"),
                    "agent": err.get("agent", ""),
                    "request_id": err.get("request_id", ""),
                    "details": err.get("details", {}),
                }
                await items.put(from_envelope(envelope))
                return

            if msg.data:
                await items.put(json.loads(msg.data))

            if is_end:
                await items.put(None)

        sub = await self._conn.subscribe(resolved, cb=_on_msg)
        await self._subscribe_pending()

        try:
            while True:
                if timeout is not None:
                    try:
                        item = await asyncio.wait_for(items.get(), timeout=timeout)
                    except TimeoutError as e:
                        raise MeshTimeout(subject=resolved, timeout=timeout) from e
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

            headers = self._with_instance_id({"X-Mesh-Request-Id": request_id})
            await self._conn.publish(subject, data, headers=headers, reply=reply_subject)
        else:
            base: dict[str, str] = {"X-Mesh-Request-Id": request_id}
            if reply_to:
                base["X-Mesh-Reply-To"] = reply_to
            headers = self._with_instance_id(base)
            await self._conn.publish(subject, data, headers=headers, reply=reply_to or "")

    async def publish(
        self: AgentMesh,
        subject: str,
        payload: BaseModel | bytes | str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Publish a payload to an arbitrary NATS subject (ADR-0058).

        Accepts:
        - ``BaseModel``: JSON-encoded via ``model_dump_json``.
        - ``bytes``: published as-is.
        - ``str``: encoded as UTF-8.

        The SDK auto-stamps OAM headers:
        - ``X-Mesh-Request-Id`` (uuid4 hex)
        - ``X-Mesh-Instance-Id`` (this mesh's id, ADR-0059)
        - ``X-Mesh-Content-Type`` (application/json | application/octet-stream | text/plain)

        User-supplied headers take priority. Wildcard subjects raise ``ValueError``.
        """
        assert self._nc is not None, "Not connected. Use 'async with mesh:' first."

        if not subject or not _VALID_PUBLISH_SUBJECT.match(subject):
            if "*" in subject or ">" in subject:
                raise ValueError(
                    f"Subject {subject!r} contains a wildcard. "
                    "Wildcards are valid only in subscriptions, not publish."
                )
            raise ValueError(f"Invalid NATS subject: {subject!r}")

        if isinstance(payload, BaseModel):
            data = payload.model_dump_json().encode()
            content_type = "application/json"
        elif isinstance(payload, bytes):
            data = payload
            content_type = "application/octet-stream"
        elif isinstance(payload, str):
            data = payload.encode()
            content_type = "text/plain"
        else:
            raise TypeError(
                f"publish payload must be BaseModel, bytes, or str; got {type(payload).__name__}"
            )

        request_id = uuid.uuid4().hex
        merged: dict[str, str] = {
            X_MESH_REQUEST_ID: request_id,
            X_MESH_CONTENT_TYPE: content_type,
        }
        merged = self._with_instance_id(merged)
        if headers:
            merged.update(headers)

        await self._conn.publish(subject, data, headers=merged)
