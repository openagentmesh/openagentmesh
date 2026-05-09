"""Dashboard backend: FastAPI app + WebSocket fan-out + mesh consumers.

Per ``.planning/phases/02-cascade-closure/02-05-PLAN.md`` and
``km/specs/wildfire/dashboard.md`` (post D-25 amendment) this module ships:

- ``make_app(mesh)``: FastAPI app with one ``/ws`` WebSocket endpoint, a
  ``/health`` smoke route, and ``dist/`` static-mounted at ``/``. The
  WebSocket fans out the four event types listed below; click writes from
  the browser route through ``handle_click`` (server-side grid snap, D-52).
- ``register_mesh_consumers(mesh, broadcast)``: four ``@mesh.agent``
  observability registrations whose source bindings turn KV updates and
  ``mesh.action.>`` pubsub into JSON envelopes pushed onto the broadcaster.
- ``handle_click``: pure click write path, broken out so unit tests can
  exercise it without standing up a real WebSocket connection.

WebSocket message protocol (server <-> browser):

Browser -> server::

    {"type": "click", "coords": {"x": <float>, "y": <float>},
     "temperature": <float | null>}

Server -> browser (one of)::

    {"type": "cell_update", "coords": {"x", "y"}, "temperature",
     "x_idx", "y_idx"}
    {"type": "cell_delete", "x_idx", "y_idx"}
    {"type": "fleet_update", "instance_id", "zone", "fleet_type",
     "coords", "state", "current_assignment", "last_updated"}
    {"type": "detection", "detection_id", "coords", "severity", "state"}
    {"type": "action_status", "subject", "payload"}

D-50 / D-53 click cycle: ``temperature == FIRE_SIM_AMBIENT_C`` (or ``None``)
maps to a ``mesh.kv.delete`` instead of a ``put_model`` so the sparse-KV
invariant holds (ambient cells have no key).

This module deliberately avoids ``mesh.publish`` and any subject_source on
the pre-amendment world-state subjects (the ones that ADR-0054's second
amendment / D-26..D-28 dropped); the dashboard reads world state purely
from the cell KV namespace.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from demos.wildfire.core.config import FIRE_SIM_AMBIENT_C
from demos.wildfire.core.contracts import (
    CellState,
    Coords,
    DetectionRecord,
    FleetMemberState,
)
from demos.wildfire.core.keys import (
    CELL_PREFIX,
    DETECTION_PREFIX,
    FLEET_PREFIX,
    cell_center,
    cell_indices,
    cell_key,
)
from openagentmesh import AgentMesh, AgentSpec, KVEntry, MeshMessage

_log = logging.getLogger("wildfire.dashboard.server")


# ---------------------------------------------------------------------------
# WebSocket message-type constants (public exports for plan 02-09 reuse)
# ---------------------------------------------------------------------------

MSG_CELL_UPDATE = "cell_update"
MSG_CELL_DELETE = "cell_delete"
MSG_FLEET_UPDATE = "fleet_update"
MSG_DETECTION = "detection"
MSG_ACTION_STATUS = "action_status"
MSG_SNAPSHOT_COMPLETE = "snapshot_complete"

Broadcast = Callable[[dict[str, Any]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Click write path (D-52 / D-53)
# ---------------------------------------------------------------------------


async def handle_click(
    mesh: AgentMesh,
    *,
    x: float,
    y: float,
    temperature: float | None,
) -> None:
    """Server-side click handler. Snap to grid; write or delete the cell.

    The grid snap is the single source of truth for cell-key derivation
    (D-52): browser clicks land on continuous coords; the server projects
    them onto the 200 m grid via ``cell_indices`` + ``cell_center`` so
    ``CellState.coords`` is always the snapped center.

    A ``temperature`` of ``None`` or ``FIRE_SIM_AMBIENT_C`` (per D-50) maps
    to ``mesh.kv.delete`` so ambient cells have no key (sparse invariant).
    A delete on an absent key is swallowed: clicking 'off' on a non-hot
    cell is a harmless no-op.
    """
    # Validate coords before touching KV. Out-of-bounds clicks (e.g. the
    # browser sends x=999) raise pydantic.ValidationError, which the
    # caller (the WebSocket loop) catches and turns into an error frame
    # without crashing the connection.
    Coords(x=x, y=y)

    x_idx, y_idx = cell_indices(x, y)
    snapped = cell_center(x_idx, y_idx)
    key = cell_key(x, y)

    if temperature is None or temperature <= FIRE_SIM_AMBIENT_C:
        # D-50: 'off' click. Delete the key so the cell decays back to
        # ambient (sparse-KV invariant). Missing key on delete is a
        # benign no-op.
        try:
            await mesh.kv.delete(key)
        except Exception as e:
            # KeyNotFoundError surfaces from nats-py on absent keys; any
            # other exception is logged but not raised so the WebSocket
            # connection survives a transient KV blip.
            _log.debug("delete %s swallowed: %s", key, e)
        return

    state = CellState(
        coords=snapped,
        temperature=temperature,
        last_modified_at=time.time(),
        last_modified_by=mesh.instance_id,
    )
    await mesh.kv.put_model(key, state)


# ---------------------------------------------------------------------------
# Key parsers (defensive: malformed keys are logged + dropped)
# ---------------------------------------------------------------------------


def _parse_cell_key(key: str) -> tuple[int, int] | None:
    """Parse ``wildfire.world.cell.<x>.<y>`` -> ``(x_idx, y_idx)`` or None."""
    if not key.startswith(CELL_PREFIX + "."):
        return None
    tail = key[len(CELL_PREFIX) + 1 :]
    parts = tail.split(".")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _parse_fleet_key(key: str) -> tuple[str, str, str] | None:
    """Parse ``wildfire.fleet.<zone>.<type>.<instance_id>``."""
    if not key.startswith(FLEET_PREFIX + "."):
        return None
    tail = key[len(FLEET_PREFIX) + 1 :]
    parts = tail.split(".")
    if len(parts) < 3:
        return None
    # instance_id MAY contain dots in pathological cases; rejoin the tail.
    zone, fleet_type, *rest = parts
    instance_id = ".".join(rest)
    return zone, fleet_type, instance_id


def _parse_detection_key(key: str) -> str | None:
    """Parse ``wildfire.detection.<detection_id>`` -> id."""
    if not key.startswith(DETECTION_PREFIX + "."):
        return None
    return key[len(DETECTION_PREFIX) + 1 :]


# ---------------------------------------------------------------------------
# Mesh consumer registration (kv_source x3 + subject_source x1)
# ---------------------------------------------------------------------------


def register_mesh_consumers(mesh: AgentMesh, broadcast: Broadcast) -> None:
    """Wire the four observability agents that turn mesh events into
    WebSocket envelopes.

    Each handler is registered under a ``dashboard.*-feed`` channel so the
    admin UI catalog shows them as observability components, not as
    scenario agents (the dashboard backend MUST NOT pollute the catalog
    with a 'fleet member'-shaped agent).

    Pattern segment-count rules (carry-forward of Phase 1 plan 01-10's
    bug discovery):

    - ``wildfire.world.cell.<x_idx>.<y_idx>`` -> two trailing segments;
      wildcard ``.>`` (one or more).
    - ``wildfire.fleet.<zone>.<type>.<instance_id>`` -> three trailing
      segments; wildcard ``.>``.
    - ``wildfire.detection.<id>`` -> one trailing segment; ``.*`` works.
    - ``mesh.action.>`` -> arbitrary suffix (channel.subchannel.event);
      ``.>`` wildcard.
    """

    @mesh.agent(
        AgentSpec(
            name="dashboard.cell-feed",
            description=(
                "Dashboard observability: forward wildfire.world.cell.> KV "
                "updates to connected WebSocket clients as cell_update / "
                "cell_delete envelopes. Read-only consumer; no side effects "
                "on the mesh."
            ),
        ),
        sources=[mesh.kv_source(f"{CELL_PREFIX}.>", on_init="replay")],
    )
    async def on_cell(entry: KVEntry[CellState]) -> None:
        parsed = _parse_cell_key(entry.key)
        if parsed is None:
            _log.warning("malformed cell key: %r", entry.key)
            return
        x_idx, y_idx = parsed
        if entry.operation == "DELETE":
            await broadcast(
                {
                    "type": MSG_CELL_DELETE,
                    "x_idx": x_idx,
                    "y_idx": y_idx,
                }
            )
            return
        # PUT op: entry.value is a validated CellState.
        cell = entry.value
        await broadcast(
            {
                "type": MSG_CELL_UPDATE,
                "coords": {"x": cell.coords.x, "y": cell.coords.y},
                "temperature": cell.temperature,
                "x_idx": x_idx,
                "y_idx": y_idx,
            }
        )

    @mesh.agent(
        AgentSpec(
            name="dashboard.fleet-feed",
            description=(
                "Dashboard observability: forward wildfire.fleet.> KV "
                "updates (FleetMemberState heartbeats) to connected "
                "WebSocket clients as fleet_update envelopes."
            ),
        ),
        sources=[mesh.kv_source(f"{FLEET_PREFIX}.>", on_init="replay")],
    )
    async def on_fleet(entry: KVEntry[FleetMemberState]) -> None:
        parsed = _parse_fleet_key(entry.key)
        if parsed is None:
            _log.warning("malformed fleet key: %r", entry.key)
            return
        zone, fleet_type, instance_id = parsed
        if entry.operation == "DELETE":
            # Rare: a fleet member's heartbeat key disappeared. Surface as
            # an offline marker so the canvas can fade the pointer.
            await broadcast(
                {
                    "type": MSG_FLEET_UPDATE,
                    "instance_id": instance_id,
                    "zone": zone,
                    "fleet_type": fleet_type,
                    "coords": None,
                    "state": "offline",
                    "current_assignment": None,
                    "last_updated": 0.0,
                }
            )
            return
        st = entry.value
        await broadcast(
            {
                "type": MSG_FLEET_UPDATE,
                "instance_id": st.instance_id,
                "zone": st.zone,
                "fleet_type": st.fleet_type,
                "coords": {"x": st.coords.x, "y": st.coords.y},
                "state": st.state,
                "current_assignment": st.current_assignment,
                "last_updated": st.last_updated,
            }
        )

    @mesh.agent(
        AgentSpec(
            name="dashboard.detection-feed",
            description=(
                "Dashboard observability: forward wildfire.detection.* KV "
                "updates to connected WebSocket clients as detection "
                "envelopes (transient flashes when a detection_id appears)."
            ),
        ),
        sources=[mesh.kv_source(f"{DETECTION_PREFIX}.*", on_init="replay")],
    )
    async def on_detection(entry: KVEntry[DetectionRecord]) -> None:
        if entry.operation == "DELETE":
            return  # detections are append-only in Phase 1/2; ignore deletes.
        rec = entry.value
        await broadcast(
            {
                "type": MSG_DETECTION,
                "detection_id": rec.detection_id,
                "coords": {"x": rec.coords.x, "y": rec.coords.y},
                "severity": rec.severity,
                "state": rec.state,
            }
        )

    @mesh.agent(
        AgentSpec(
            name="dashboard.action-feed",
            description=(
                "Dashboard observability: forward mesh.action.> pubsub "
                "(HeliStatus / FFUnitStatus / MedevacStatus) to connected "
                "WebSocket clients as action_status envelopes."
            ),
        ),
        sources=[mesh.subject_source("mesh.action.>")],
    )
    async def on_action_status(msg: MeshMessage[bytes]) -> None:
        # Status payload type varies by subject (heli/ffunit/medevac).
        # Decode generically; the browser side knows the subject.
        try:
            payload = json.loads(msg.payload) if msg.payload else None
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            _log.warning(
                "malformed JSON on %s: %s; payload=%r", msg.subject, e, msg.payload
            )
            return
        await broadcast(
            {
                "type": MSG_ACTION_STATUS,
                "subject": msg.subject,
                "payload": payload,
            }
        )


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def make_app(mesh: AgentMesh) -> FastAPI:
    """Build the FastAPI app. Caller is responsible for calling
    :func:`register_mesh_consumers` (typically right after this) to wire
    the broadcaster.

    The returned app exposes:

    - ``GET /health``: 200 with ``{status, mesh_instance_id, connections}``.
    - ``WS /ws``: bidirectional WebSocket. Browser -> server: ``click``
      messages. Server -> browser: the five envelope types defined above.
    - ``GET /``: static mount on ``demos/wildfire/dashboard/dist/`` if
      present; absent dist is non-fatal here (the ``__main__.py`` boot
      path verifies presence and exits with a clear stderr message).
    """
    app = FastAPI(title="wildfire-dashboard")

    connections: list[WebSocket] = []

    async def broadcast(message: dict[str, Any]) -> None:
        """Send a JSON envelope to every connected WebSocket. Connections
        that raise on send are dropped silently (they will be GCed when
        the disconnect handler fires)."""
        # Snapshot the list because send() can mutate it via the disconnect
        # path; iterate over a copy.
        dead: list[WebSocket] = []
        for ws in list(connections):
            try:
                await ws.send_json(message)
            except Exception as e:
                _log.debug("dropping ws connection: %s", e)
                dead.append(ws)
        for ws in dead:
            try:
                connections.remove(ws)
            except ValueError:
                pass

    app.state.broadcast = broadcast
    app.state.connections = connections

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mesh_instance_id": mesh.instance_id,
            "connections": len(connections),
        }

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        connections.append(websocket)
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError as e:
                    _log.warning("malformed JSON from ws: %s; raw=%r", e, raw)
                    continue
                if not isinstance(msg, dict):
                    _log.warning("non-object ws frame: %r", msg)
                    continue
                msg_type = msg.get("type")
                if msg_type == "click":
                    coords = msg.get("coords") or {}
                    try:
                        x = float(coords.get("x"))
                        y = float(coords.get("y"))
                    except (TypeError, ValueError) as e:
                        _log.warning("click frame missing coords: %s; raw=%r", e, msg)
                        continue
                    raw_temp = msg.get("temperature")
                    temperature: float | None
                    if raw_temp is None:
                        temperature = None
                    else:
                        try:
                            temperature = float(raw_temp)
                        except (TypeError, ValueError):
                            _log.warning("click frame bad temperature: %r", raw_temp)
                            continue
                    try:
                        await handle_click(
                            mesh, x=x, y=y, temperature=temperature
                        )
                    except ValidationError as e:
                        # Out-of-bounds coords reject here. Reply with an
                        # error frame so the browser can surface it; do
                        # NOT crash the connection.
                        try:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "reason": "invalid_coords",
                                    "details": str(e),
                                }
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        _log.warning("click handler raised: %s", e)
                else:
                    _log.warning("unknown ws frame type: %r", msg_type)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            _log.warning("ws loop ended: %s", e)
        finally:
            try:
                connections.remove(websocket)
            except ValueError:
                pass

    # Mount static dist/ at /. If dist is missing the make_app() call still
    # succeeds; the __main__ entry point verifies presence at boot and
    # surfaces a clear "run pnpm run build" message before uvicorn starts.
    dist_dir = Path(__file__).parent / "dist"
    if dist_dir.is_dir():
        app.mount(
            "/", StaticFiles(directory=str(dist_dir), html=True), name="dist"
        )

    return app


__all__ = [
    "MSG_ACTION_STATUS",
    "MSG_CELL_DELETE",
    "MSG_CELL_UPDATE",
    "MSG_DETECTION",
    "MSG_FLEET_UPDATE",
    "MSG_SNAPSHOT_COMPLETE",
    "Broadcast",
    "handle_click",
    "make_app",
    "register_mesh_consumers",
]


# Avoid "imported but unused" lints for asyncio in environments where the
# import-cycle elision drops it. asyncio is referenced indirectly through
# FastAPI's lifecycle, but we keep the explicit import so static analysis
# can confirm a Python 3.11+ asyncio capability surface.
_ = asyncio
