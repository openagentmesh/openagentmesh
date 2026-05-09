"""Shared base class for action fleets (heli / ffunit / medevac), per D-41/D-46.

Encapsulates the lifecycle (dispatched -> en_route -> on_site -> acting ->
returning -> free), the single-writer task that owns all KV writes for the
agent's own ``FleetMemberState`` record, the per-transition status pubsub
helper, and the ETA formula. Subclasses parametrise speed / action duration
and override ``_make_status()`` to return the per-fleet status BaseModel.

Key invariants:

  - **Single-writer pattern (D-41):** only ``_writer_loop`` calls
    ``mesh.kv.put_model`` for the agent's own record. Handler enqueues
    a ``_Transition``; never writes directly. No ``asyncio.Lock`` and
    no CAS for the agent's own record (CAS stays the cross-agent
    coordination primitive).

  - **Heartbeat collapses into the writer's idle branch (D-41):** when
    ``HEARTBEAT_INTERVAL_S`` elapses with no transition, the writer
    re-stamps the same ``FleetMemberState`` with a fresh ``last_updated``.
    No separate heartbeat task.

  - **Handler returns ack quickly (D-42):** decide accept/reject, enqueue
    one transition, spawn ``asyncio.create_task(_simulate(order))``, return
    ``DispatchAck``. Simulation is fire-and-forget.

  - **Busy reject (D-44):** if a second order arrives while the agent is
    mid-dispatch, the handler returns ``DispatchAck(accepted=False,
    reason="busy")`` immediately. Queue group routes to another instance.

  - **Status pubsub on every transition (D-45):** publish a per-fleet
    status BaseModel on ``mesh.action.{fleet_type}.{instance_id}.status``
    after each state change.

  - **3-state ⟷ 6-state mapping for FleetMemberState.state:**

      - ``ActionState`` "free" -> ``FleetMemberState.state`` "free",
        ``current_assignment=None``.
      - ``ActionState`` in {"dispatched", "en_route", "on_site",
        "acting", "returning"} -> ``FleetMemberState.state`` "busy",
        ``current_assignment=order_id``.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from demos.wildfire.core.config import HEARTBEAT_INTERVAL_S, HQ
from demos.wildfire.core.contracts import (
    ActionState,
    Coords,
    DispatchAck,
    DispatchOrder,
    FleetMemberState,
)
from demos.wildfire.core.keys import fleet_key

if TYPE_CHECKING:
    from openagentmesh import AgentMesh

_log = logging.getLogger("wildfire.fleet.action")


# ---------------------------------------------------------------------------
# Single-writer queue messages
# ---------------------------------------------------------------------------


@dataclass
class _Transition:
    """Lifecycle transition payload sent to the writer task."""

    state: ActionState
    coords: Coords
    order_id: str | None
    current_assignment: str | None


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class ActionFleetAgent:
    """Shared lifecycle + KV + pubsub plumbing for action-fleet agents (D-46).

    Subclasses (HeliAgent, FFUnitAgent, MedevacAgent) override:

      - ``_make_status(state, order_id, coords) -> BaseModel`` to return
        the per-fleet status payload (HeliStatus / FFUnitStatus /
        MedevacStatus).

      - Optionally ``_act(order)`` to run a custom in-place action body
        (default: ``await asyncio.sleep(self.action_duration_s)``).

    The ``register_handler(mesh, *, name, description)`` helper wires the
    ``@mesh.agent`` decorator and binds the handler to ``self.handle``.
    Module-level subclass code stays a couple of lines.
    """

    def __init__(
        self,
        mesh: AgentMesh,
        *,
        zone: str,
        fleet_type: str,
        speed_km_s: float,
        action_duration_s: float,
        home: Coords | None = None,
    ) -> None:
        self.mesh = mesh
        self.zone = zone
        self.fleet_type = fleet_type
        self.speed_km_s = speed_km_s
        self.action_duration_s = action_duration_s
        self._home: Coords = home if home is not None else HQ
        self._coords: Coords = self._home
        self._state: ActionState = "free"
        self._order: DispatchOrder | None = None
        self._writer_queue: asyncio.Queue[_Transition | None] = asyncio.Queue()
        self._sim_task: asyncio.Task | None = None
        self._writer_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle: start / stop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn the single-writer task. Idempotent."""
        if self._writer_task is None or self._writer_task.done():
            self._writer_task = asyncio.create_task(self._writer_loop())

    async def stop(self) -> None:
        """Cancel writer + simulation tasks and wait for them to drain."""
        for task in (self._sim_task, self._writer_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._sim_task, self._writer_task):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._sim_task = None
        self._writer_task = None

    async def __aenter__(self) -> ActionFleetAgent:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Handler entry point
    # ------------------------------------------------------------------

    async def handle(self, order: DispatchOrder) -> DispatchAck:
        """Accept-or-reject a DispatchOrder. Spawns the simulation on accept (D-42)."""
        # Busy reject (D-44): another dispatch is in progress.
        if self._state != "free" or self._sim_task is not None and not self._sim_task.done():
            return DispatchAck(
                accepted=False,
                instance_id=self.mesh.instance_id,
                eta_seconds=None,
                reason="busy",
            )

        eta = self._eta(order)
        # Mark intent; the writer will publish the "dispatched" transition.
        self._state = "dispatched"
        self._order = order
        await self._writer_queue.put(
            _Transition(
                state="dispatched",
                coords=self._coords,
                order_id=order.order_id,
                current_assignment=order.order_id,
            )
        )
        self._sim_task = asyncio.create_task(self._simulate(order))
        return DispatchAck(
            accepted=True,
            instance_id=self.mesh.instance_id,
            eta_seconds=eta,
            reason=None,
        )

    # ------------------------------------------------------------------
    # ETA formula (D-43)
    # ------------------------------------------------------------------

    def _eta(self, order: DispatchOrder) -> float:
        """ETA = straight-line distance / speed + action duration (D-43).

        Note: the formula intentionally omits the return leg; the operator
        cares about time-to-effect, not time-to-home.
        """
        dist = math.hypot(
            self._coords.x - order.target_coords.x,
            self._coords.y - order.target_coords.y,
        )
        return dist / self.speed_km_s + self.action_duration_s

    # ------------------------------------------------------------------
    # Simulation lifecycle (transit -> action -> return)
    # ------------------------------------------------------------------

    async def _simulate(self, order: DispatchOrder) -> None:
        """Drive the dispatched -> en_route -> on_site -> acting -> returning -> free
        transitions, sleeping a slice proportional to distance/speed for
        each leg and ``action_duration_s`` for the in-place action.
        """
        try:
            target = order.target_coords
            home = self._home

            transit_time = math.hypot(
                self._coords.x - target.x, self._coords.y - target.y,
            ) / self.speed_km_s

            # 1. en_route
            self._state = "en_route"
            await self._writer_queue.put(
                _Transition(
                    state="en_route",
                    coords=self._coords,
                    order_id=order.order_id,
                    current_assignment=order.order_id,
                )
            )
            await asyncio.sleep(transit_time)

            # 2. on_site
            self._coords = target
            self._state = "on_site"
            await self._writer_queue.put(
                _Transition(
                    state="on_site",
                    coords=self._coords,
                    order_id=order.order_id,
                    current_assignment=order.order_id,
                )
            )

            # 3. acting (in-place action body — overridable)
            self._state = "acting"
            await self._writer_queue.put(
                _Transition(
                    state="acting",
                    coords=self._coords,
                    order_id=order.order_id,
                    current_assignment=order.order_id,
                )
            )
            await self._act(order)

            # 4. returning
            return_time = math.hypot(
                self._coords.x - home.x, self._coords.y - home.y,
            ) / self.speed_km_s
            self._state = "returning"
            await self._writer_queue.put(
                _Transition(
                    state="returning",
                    coords=self._coords,
                    order_id=order.order_id,
                    current_assignment=order.order_id,
                )
            )
            await asyncio.sleep(return_time)

            # 5. free
            self._coords = home
            self._state = "free"
            self._order = None
            await self._writer_queue.put(
                _Transition(
                    state="free",
                    coords=self._coords,
                    order_id=None,
                    current_assignment=None,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception(
                "%s simulation crashed for order %s",
                self.fleet_type, order.order_id,
            )
        finally:
            self._sim_task = None

    async def _act(self, order: DispatchOrder) -> None:
        """In-place action body. Override to add fleet-specific logging /
        side effects (e.g. writing cooler cells for closed-loop suppression).
        """
        await asyncio.sleep(self.action_duration_s)

    # ------------------------------------------------------------------
    # Writer task (single owner of own KV record + status pubsub)
    # ------------------------------------------------------------------

    async def _writer_loop(self) -> None:
        """Single owner of own-KV-record writes + status pubsub.

        Receives ``_Transition`` messages from the queue, applies the
        FleetMemberState 3-state mapping, writes KV, publishes status. On
        timeout (no transition for ``HEARTBEAT_INTERVAL_S``), re-stamps the
        existing record with a fresh ``last_updated`` (collapsed heartbeat
        per D-41).
        """
        key = fleet_key(self.zone, self.fleet_type, self.mesh.instance_id)

        async def _idle_write() -> None:
            await self._safe_kv_put(key, self._snapshot_member_state())

        # Initial heartbeat so liveness shows up promptly.
        await _idle_write()

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(
                        self._writer_queue.get(),
                        timeout=HEARTBEAT_INTERVAL_S,
                    )
                except TimeoutError:
                    # Idle branch: tick last_updated.
                    await _idle_write()
                    continue

                if msg is None:
                    # Sentinel for explicit shutdown (currently unused).
                    return

                # Apply transition: position is mostly already mutated by
                # _simulate, but we trust the writer-queue payload as the
                # source of truth.
                self._coords = msg.coords
                self._state = msg.state
                # Subclass hook BEFORE status publish: lets subclasses mutate
                # state that should be reflected in the published status
                # (e.g. medevac capacity_used) within the same writer tick.
                self._on_transition(state=msg.state, order_id=msg.order_id)
                await self._safe_kv_put(key, self._build_member_state(msg))
                await self._safe_publish_status(
                    state=msg.state,
                    order_id=msg.order_id,
                    coords=msg.coords,
                )
        except asyncio.CancelledError:
            return

    def _snapshot_member_state(self) -> FleetMemberState:
        """Build a FleetMemberState reflecting current in-memory state (idle path)."""
        if self._state == "free":
            fs_state = "free"
            assignment = None
        else:
            fs_state = "busy"
            assignment = self._order.order_id if self._order is not None else None
        return FleetMemberState(
            instance_id=self.mesh.instance_id,
            zone=self.zone,  # type: ignore[arg-type]
            fleet_type=self.fleet_type,  # type: ignore[arg-type]
            coords=self._coords,
            state=fs_state,
            current_assignment=assignment,
            last_updated=time.time(),
        )

    def _build_member_state(self, msg: _Transition) -> FleetMemberState:
        """Build a FleetMemberState from an inbound _Transition payload."""
        if msg.state == "free":
            fs_state = "free"
            assignment = None
        else:
            fs_state = "busy"
            assignment = msg.current_assignment
        return FleetMemberState(
            instance_id=self.mesh.instance_id,
            zone=self.zone,  # type: ignore[arg-type]
            fleet_type=self.fleet_type,  # type: ignore[arg-type]
            coords=msg.coords,
            state=fs_state,
            current_assignment=assignment,
            last_updated=time.time(),
        )

    async def _safe_kv_put(self, key: str, record: FleetMemberState) -> None:
        try:
            await self.mesh.kv.put_model(key, record)
        except Exception as e:
            _log.warning("KV write failed for %s: %s", key, e)

    async def _safe_publish_status(
        self,
        *,
        state: ActionState,
        order_id: str | None,
        coords: Coords,
    ) -> None:
        try:
            payload = self._make_status(
                state=state, order_id=order_id, coords=coords,
            )
            await self.mesh.publish(self._status_subject(), payload)
        except Exception as e:
            _log.warning(
                "status publish failed for %s.%s: %s",
                self.fleet_type, self.mesh.instance_id, e,
            )

    # ------------------------------------------------------------------
    # Subclass extension points
    # ------------------------------------------------------------------

    def _status_subject(self) -> str:
        """Per-fleet status subject. Format: ``mesh.action.{fleet_type}.{instance_id}.status``."""
        return f"mesh.action.{self.fleet_type}.{self.mesh.instance_id}.status"

    def _make_status(
        self,
        *,
        state: ActionState,
        order_id: str | None,
        coords: Coords,
    ) -> BaseModel:
        """Subclasses MUST override to return a per-fleet status BaseModel."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement _make_status()"
        )

    def _on_transition(
        self,
        *,
        state: ActionState,
        order_id: str | None,
    ) -> None:
        """Subclass hook called by the writer immediately after each transition.

        Default: no-op. Subclasses override to mutate per-fleet state that
        the next ``_make_status()`` call should reflect (e.g. medevac
        ``capacity_used`` increments on entering ``"acting"`` and resets on
        re-entering ``"free"``). Synchronous; runs inside the writer task,
        so no concurrency hazards.
        """
        return None

    # ------------------------------------------------------------------
    # @mesh.agent registration helper
    # ------------------------------------------------------------------

    def register_handler(
        self,
        mesh: AgentMesh,
        *,
        name: str,
        description: str,
    ) -> None:
        """Bind a ``@mesh.agent(AgentSpec(...))`` Responder that delegates to ``self.handle``.

        Subclass modules use this so each per-fleet ``_main()`` only needs to
        instantiate, register, and run.
        """
        # Lazy import to keep this module unit-testable in isolation.
        from openagentmesh._models import AgentSpec  # noqa: PLC0415

        @mesh.agent(AgentSpec(name=name, description=description))
        async def _responder(order: DispatchOrder) -> DispatchAck:
            return await self.handle(order)
