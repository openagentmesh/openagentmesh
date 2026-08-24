"""Tests for the Wildfire Incident Response cookbook recipe.

Executable version of the code samples in docs/cookbook/wildfire-incident.md:
same models, same agents, same main(), plus assertions. Each test uses
AgentMesh.local() for a fully isolated embedded NATS instance.
"""

import asyncio
import contextlib
import hashlib
import time
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from openagentmesh import AgentMesh, AgentSpec, KVEntry, KVKeyExists

# --- Contracts (same as docs/cookbook/wildfire-incident.md) ---


class Coords(BaseModel):
    x: float = Field(ge=-5.0, le=5.0)  # km from HQ at the origin
    y: float = Field(ge=-5.0, le=5.0)


class CellState(BaseModel):
    """KV value at wildfire.world.cell.<x_idx>.<y_idx> (200 m grid)."""
    coords: Coords
    temperature: float  # degrees Celsius


class SurveyResult(BaseModel):
    surveyor_instance_id: str
    fire_visible: bool
    persons_detected: int


class DetectionRecord(BaseModel):
    """KV value at wildfire.detection.{detection_id}.

    Lifecycle: pending -> assigned:{instance_id} -> surveyed.
    """
    detection_id: str
    state: str
    coords: Coords
    severity: float  # 0..1, derived from temperature
    survey: SurveyResult | None = None


class TaskRequest(BaseModel):
    operator_id: str
    text: str  # natural language from the operator


class TaskCommand(BaseModel):
    target_fleet: Literal["heli", "ffunit", "medevac"]
    coords: Coords
    priority: Literal["low", "med", "high"]
    persons_estimated: int = 0
    rationale: str  # one line, for the audit log


# --- Pattern 1: KV-driven detection (UAV) ---


TEMP_THRESHOLD_C = 100.0


def dedup_id(coords: Coords, now: float) -> str:
    """One detection per 100 m grid bucket per 30 s window."""
    bucket = f"{round(coords.x / 0.1)}:{round(coords.y / 0.1)}:{int(now // 30)}"
    return hashlib.sha1(bucket.encode()).hexdigest()[:16]


def build_uav(mesh: AgentMesh) -> None:
    @mesh.agent(
        AgentSpec(
            name="high-alt.uav",
            description="High-altitude thermal observer; writes pending "
                        "detections from world-cell updates.",
        ),
        sources=[mesh.kv_source("wildfire.world.cell.>", on_init="replay")],
    )
    async def uav(entry: KVEntry[CellState]) -> None:
        if entry.operation == "DELETE":
            return  # cell cooled back to ambient; detections are not retracted

        cell = entry.value
        if cell.temperature <= TEMP_THRESHOLD_C:
            return

        detection_id = dedup_id(cell.coords, time.time())
        record = DetectionRecord(
            detection_id=detection_id,
            state="pending",
            coords=cell.coords,
            severity=min(1.0, (cell.temperature - 100.0) / 700.0),
        )
        # KVKeyExists means this area was already reported in this window:
        # the create is the dedup.
        with contextlib.suppress(KVKeyExists):
            await mesh.kv.create(f"wildfire.detection.{detection_id}", record)


# --- Pattern 2: Leaderless task election (drone) ---


def build_drone(mesh: AgentMesh) -> None:
    @mesh.agent(
        AgentSpec(
            name="low-alt.drone",
            description="Low-altitude survey drone; CAS-elects itself on "
                        "pending detections and writes the survey result.",
        ),
        sources=[mesh.kv_source("wildfire.detection.*", on_init="replay")],
    )
    async def drone(entry: KVEntry[DetectionRecord]) -> None:
        if entry.operation == "DELETE":
            return
        rec = entry.value
        if rec.state != "pending":
            return

        key = f"wildfire.detection.{rec.detection_id}"

        # Election: one CAS attempt. Losing the race is data, not an error.
        async with mesh.kv.try_cas_model(key, DetectionRecord) as claim:
            if claim.value.state != "pending":
                return  # claimed between the event and our read
            claim.value.state = f"assigned:{mesh.instance_id}"
        if not claim.committed:
            return  # another drone won

        await asyncio.sleep(0.1)  # simulate travel + sensor sweep

        async with mesh.kv.try_cas_model(key, DetectionRecord) as done:
            done.value.state = "surveyed"
            done.value.survey = SurveyResult(
                surveyor_instance_id=mesh.instance_id,
                fire_visible=True,
                persons_detected=0,
            )


# --- Pattern 3: LLM peer as a plain typed agent (tasker) ---


def build_tasker(mesh: AgentMesh) -> None:
    @mesh.agent(AgentSpec(
        name="tasker",
        description="Translates an operator's natural-language request into "
                    "one typed TaskCommand. Do NOT use it to execute or "
                    "dispatch anything: it only translates.",
    ))
    async def tasker(req: TaskRequest) -> TaskCommand:
        # Ground in live mesh state: target the newest surveyed detection.
        detections = await mesh.kv.list_models(
            "wildfire.detection.>", DetectionRecord,
        )
        surveyed = [e.value for e in detections if e.value.state == "surveyed"]
        target = surveyed[-1].coords if surveyed else Coords(x=0.0, y=0.0)

        # Stand-in for one structured LLM call (see the recipe).
        text = req.text.lower()
        wants_extraction = "person" in text or "extract" in text
        return TaskCommand(
            target_fleet="medevac" if wants_extraction else "heli",
            coords=target,
            priority="high" if ("urgent" in text or "now" in text) else "med",
            rationale=f"Translated from operator {req.operator_id} request.",
        )


# --- The cascade driver (same as docs) ---


async def main(mesh: AgentMesh) -> None:
    build_uav(mesh)
    build_drone(mesh)
    build_tasker(mesh)
    await mesh.catalog()      # flush registrations: KV sources bind, agents go live
    await asyncio.sleep(0.1)  # let the watchers attach

    # Ignite: write one burning cell. Nobody dispatches anything.
    await mesh.kv.put_model(
        "wildfire.world.cell.31.21",
        CellState(coords=Coords(x=1.2, y=-0.8), temperature=620.0),
    )

    # Watch the detection record walk its lifecycle.
    async def until_surveyed() -> DetectionRecord:
        async for value in mesh.kv.watch("wildfire.detection.*"):
            rec = DetectionRecord.model_validate_json(value)
            print(f"detection {rec.detection_id}: {rec.state}")
            if rec.state == "surveyed":
                return rec

    rec = await asyncio.wait_for(until_surveyed(), timeout=10.0)
    assert rec.survey is not None  # a surveyed detection always carries its result
    print(f"survey: fire_visible={rec.survey.fire_visible}")

    # Operator speaks; the mesh answers with a typed, validated command.
    result = await mesh.call(
        "tasker",
        TaskRequest(operator_id="op-1", text="Send the water bomber, urgent"),
    )
    command = TaskCommand.model_validate(result)
    print(f"dispatch: {command.target_fleet} -> "
          f"({command.coords.x}, {command.coords.y}) [{command.priority}]")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWildfireIncidentRecipe:
    async def test_main_completes(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)

    async def test_cascade_reaches_surveyed(self):
        async with AgentMesh.local() as mesh:
            await main(mesh)

            entries = await mesh.kv.list_models(
                "wildfire.detection.>", DetectionRecord,
            )
            surveyed = [e.value for e in entries if e.value.state == "surveyed"]
            assert len(surveyed) == 1
            assert surveyed[0].survey is not None
            assert surveyed[0].survey.fire_visible
            assert surveyed[0].severity == pytest.approx((620.0 - 100.0) / 700.0)

    async def test_detection_dedup_one_record_per_window(self):
        """Two hot writes to the same cell inside one window -> one record."""
        async with AgentMesh.local() as mesh:
            build_uav(mesh)
            await mesh.catalog()
            await asyncio.sleep(0.1)

            # Guard: if the 30 s dedup window is about to roll over, wait it
            # out so both writes land in the same window deterministically.
            if time.time() % 30 > 28:
                await asyncio.sleep(2.5)

            coords = Coords(x=1.2, y=-0.8)
            await mesh.kv.put_model(
                "wildfire.world.cell.31.21",
                CellState(coords=coords, temperature=500.0),
            )
            await asyncio.sleep(0.2)
            await mesh.kv.put_model(
                "wildfire.world.cell.31.21",
                CellState(coords=coords, temperature=650.0),
            )
            await asyncio.sleep(0.3)

            entries = await mesh.kv.list_models(
                "wildfire.detection.>", DetectionRecord,
            )
            assert len(entries) == 1
            assert entries[0].value.state == "pending"

    async def test_tasker_translates_extraction_to_medevac(self):
        async with AgentMesh.local() as mesh:
            build_tasker(mesh)

            result = await mesh.call(
                "tasker",
                TaskRequest(
                    operator_id="op-1",
                    text="Two persons trapped near the ridge, extract them now",
                ),
            )
            command = TaskCommand.model_validate(result)
            assert command.target_fleet == "medevac"
            assert command.priority == "high"
