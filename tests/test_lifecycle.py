"""Tests for ADR-0055: agent lifecycle gates (active_when)."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from openagentmesh import (
    AgentMesh,
    AgentSpec,
    KVCondition,
    MeshTimeout,
    NotAvailable,
    NotFound,
    SubjectCondition,
)


class IncidentBrief(BaseModel):
    summary: str


class TaskAssignment(BaseModel):
    task: str


def _incident_active(v: bytes | None) -> bool:
    return json.loads(v) == "active" if v else False


async def _wait_for(predicate, timeout: float = 5.0, interval: float = 0.05):
    """Poll an async predicate until true or the deadline passes."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        if await predicate():
            return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(interval)


class TestKVCondition:
    async def test_gated_agent_offline_until_condition_true(self):
        """The ADR-0055 code sample: gate opens when incident.mode becomes active."""
        async with AgentMesh.local() as mesh:

            @mesh.agent(
                AgentSpec(
                    name="wildfire.coordinator",
                    description="Assigns tasks to response fleets during active wildfire incidents",
                ),
                active_when=mesh.kv_condition("incident.mode", _incident_active),
            )
            async def coordinator(brief: IncidentBrief) -> TaskAssignment:
                return TaskAssignment(task=f"handle: {brief.summary}")

            await mesh._subscribe_pending()

            # Gate closed: the agent is registered but not subscribed.
            with pytest.raises(NotAvailable):
                await mesh.call("wildfire.coordinator", {"summary": "smoke"}, timeout=2.0)

            # Open the gate.
            await mesh.kv.put("incident.mode", json.dumps("active"))

            async def _up():
                try:
                    result = await mesh.call(
                        "wildfire.coordinator", {"summary": "smoke"}, timeout=2.0
                    )
                    return result["task"] == "handle: smoke"
                except NotAvailable:
                    return False

            await _wait_for(_up)

    async def test_gate_closes_and_reopens(self):
        async with AgentMesh.local() as mesh:

            @mesh.agent(
                AgentSpec(name="gated.echo", description="echoes while enabled"),
                active_when=mesh.kv_condition("gates.echo", lambda v: v == b"on"),
            )
            async def echo(brief: IncidentBrief) -> TaskAssignment:
                return TaskAssignment(task=brief.summary)

            await mesh._subscribe_pending()
            await mesh.kv.put("gates.echo", "on")

            async def _up():
                try:
                    await mesh.call("gated.echo", {"summary": "hi"}, timeout=2.0)
                    return True
                except NotAvailable:
                    return False

            await _wait_for(_up)

            # Close the gate: the agent unsubscribes.
            await mesh.kv.put("gates.echo", "off")

            async def _down():
                try:
                    await mesh.call("gated.echo", {"summary": "hi"}, timeout=2.0)
                    return False
                except NotAvailable:
                    return True
                except MeshTimeout:
                    # A request racing the closing gate can be dropped and
                    # time out; the next probe sees not_available.
                    return False

            await _wait_for(_down, timeout=10.0)

            # Reopen: the agent comes back.
            await mesh.kv.put("gates.echo", "on")
            await _wait_for(_up)

    async def test_not_available_is_distinct_from_not_found(self):
        """Gated-offline → not_available; unregistered → not_found."""
        async with AgentMesh.local() as mesh:

            @mesh.agent(
                AgentSpec(name="gated.sleeper", description="offline until enabled"),
                active_when=mesh.kv_condition("gates.sleeper", lambda v: v == b"on"),
            )
            async def sleeper(brief: IncidentBrief) -> TaskAssignment:
                return TaskAssignment(task="zzz")

            await mesh._subscribe_pending()

            with pytest.raises(NotAvailable) as exc_info:
                await mesh.call("gated.sleeper", {"summary": "x"}, timeout=2.0)
            assert exc_info.value.code == "not_available"

            with pytest.raises(NotFound):
                await mesh.call("no.such.agent", {"summary": "x"}, timeout=2.0)

    async def test_gated_agent_stays_in_catalog(self):
        """Catalog describes capability, not availability (ADR-0055)."""
        async with AgentMesh.local() as mesh:

            @mesh.agent(
                AgentSpec(name="gated.listed", description="in catalog even while offline"),
                active_when=mesh.kv_condition("gates.listed", lambda v: v == b"on"),
            )
            async def listed(brief: IncidentBrief) -> TaskAssignment:
                return TaskAssignment(task="ok")

            await mesh._subscribe_pending()

            contracts = await mesh.discover()
            assert "gated.listed" in [c.name for c in contracts]

    async def test_initial_true_starts_online(self):
        """initial=True brings the agent up before any KV value exists."""
        async with AgentMesh.local() as mesh:

            @mesh.agent(
                AgentSpec(name="gated.default-on", description="online unless disabled"),
                active_when=mesh.kv_condition(
                    "gates.default-on", lambda v: v != b"off", initial=True
                ),
            )
            async def default_on(brief: IncidentBrief) -> TaskAssignment:
                return TaskAssignment(task="up")

            await mesh._subscribe_pending()

            result = await mesh.call("gated.default-on", {"summary": "x"}, timeout=2.0)
            assert result["task"] == "up"

    async def test_startup_reads_existing_kv_value(self):
        """A gate whose key is already true at __aenter__ comes up deterministically."""
        mesh = AgentMesh()

        @mesh.agent(
            AgentSpec(name="gated.preset", description="gate already open at startup"),
            active_when=mesh.kv_condition("gates.preset", lambda v: v == b"on"),
        )
        async def preset(brief: IncidentBrief) -> TaskAssignment:
            return TaskAssignment(task="preset-up")

        async with mesh.local():
            await mesh.kv.put("gates.preset", "on")
            # Re-entering the subscribe path evaluates the current value.
            mesh._subscribed.discard("gated.preset")
            await mesh._subscribe_pending()

            result = await mesh.call("gated.preset", {"summary": "x"}, timeout=2.0)
            assert result["task"] == "preset-up"

    async def test_drain_lets_in_flight_requests_complete(self):
        """Closing the gate mid-request drains instead of dropping."""
        async with AgentMesh.local() as mesh:
            entered = asyncio.Event()

            @mesh.agent(
                AgentSpec(name="gated.slow", description="slow worker"),
                active_when=mesh.kv_condition("gates.slow", lambda v: v == b"on"),
            )
            async def slow(brief: IncidentBrief) -> TaskAssignment:
                entered.set()
                await asyncio.sleep(0.5)
                return TaskAssignment(task="finished")

            await mesh._subscribe_pending()
            await mesh.kv.put("gates.slow", "on")

            async def _up():
                try:
                    await mesh.call("gated.slow", {"summary": "warm"}, timeout=3.0)
                    return True
                except NotAvailable:
                    return False

            await _wait_for(_up)
            entered.clear()  # the warm-up call set it; track the real request

            call_task = asyncio.ensure_future(
                mesh.call("gated.slow", {"summary": "work"}, timeout=5.0)
            )
            await asyncio.wait_for(entered.wait(), timeout=3.0)

            # Close the gate while the handler is mid-flight.
            await mesh.kv.put("gates.slow", "off")

            result = await call_task
            assert result["task"] == "finished"


class TestGatedSources:
    async def test_sources_fire_only_while_gate_open(self):
        async with AgentMesh.local() as mesh:
            received: list[IncidentBrief] = []

            @mesh.agent(
                AgentSpec(name="gated.monitor", description="watches only during incidents"),
                sources=[mesh.subject_source("test.perimeter.readings")],
                active_when=mesh.kv_condition("incident.mode", _incident_active),
            )
            async def monitor(reading: IncidentBrief) -> None:
                received.append(reading)

            await mesh._subscribe_pending()

            # Gate closed: source messages do not reach the handler.
            await mesh.publish("test.perimeter.readings", IncidentBrief(summary="ignored"))
            await mesh._conn.flush()
            await asyncio.sleep(0.2)
            assert received == []

            # Gate open: the source binds and live messages flow.
            await mesh.kv.put("incident.mode", json.dumps("active"))

            async def _delivered():
                await mesh.publish("test.perimeter.readings", IncidentBrief(summary="seen"))
                await mesh._conn.flush()
                await asyncio.sleep(0.1)
                return any(r.summary == "seen" for r in received)

            await _wait_for(_delivered)
            assert all(r.summary != "ignored" for r in received)


class TestSubjectCondition:
    async def test_subject_condition_gates_on_messages(self):
        async with AgentMesh.local() as mesh:

            @mesh.agent(
                AgentSpec(name="gated.by-subject", description="follows control messages"),
                active_when=mesh.subject_condition(
                    "control.gate", lambda payload: payload == b"open"
                ),
            )
            async def by_subject(brief: IncidentBrief) -> TaskAssignment:
                return TaskAssignment(task="via-subject")

            await mesh._subscribe_pending()

            with pytest.raises(NotAvailable):
                await mesh.call("gated.by-subject", {"summary": "x"}, timeout=2.0)

            await mesh.publish("control.gate", b"open")

            async def _up():
                try:
                    await mesh.call("gated.by-subject", {"summary": "x"}, timeout=2.0)
                    return True
                except NotAvailable:
                    return False

            await _wait_for(_up)


class TestConditionFactories:
    def test_kv_condition_shape(self):
        mesh = AgentMesh()
        cond = mesh.kv_condition("some.key", lambda v: v is not None)
        assert isinstance(cond, KVCondition)
        assert cond.key == "some.key"
        assert cond.initial is False
        assert cond.drain_timeout == 30.0

    def test_subject_condition_shape(self):
        mesh = AgentMesh()
        cond = mesh.subject_condition("some.subject", lambda v: True, initial=True)
        assert isinstance(cond, SubjectCondition)
        assert cond.subject == "some.subject"
        assert cond.initial is True
