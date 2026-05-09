"""Phase 2 cascade integration test (D-21 extension, cascade closure).

Boots the full Phase 2 demo via subprocess (``python -m demos.wildfire``),
verifies the Phase 1 cascade still completes (spawn fire -> UAV detect ->
drone CAS-survey -> ``state="surveyed"``), then exercises the action-fleet
warm-dispatch path twice (heli + medevac) via ``mesh.call`` and asserts the
matching status pubsub frames arrive on
``mesh.action.{fleet_type}.*.status`` (per-fleet wildcard; ``>`` is
terminal-only in NATS subject grammar).

Also smoke-checks the scenario UI dashboard backend (``/health`` 200 with
``mesh_instance_id`` field) and the admin UI's ``/config.json`` endpoint
(regression net for plan 02-08's ``EventFeed`` addition).

Gated by ``OAM_INTEGRATION_TESTS=1``. Boots ~16 subprocesses
(NATS + 13 fleet members + admin UI + dashboard backend), takes 60-90 s
end-to-end, requires ``pnpm`` to build admin UI + dashboard bundles.

Manual invocation::

    OAM_INTEGRATION_TESTS=1 uv run pytest tests/wildfire/integration -x -q -s

Port mental model:

* ``4222`` -- embedded NATS standard listener (the test connects its
  side-channel client here).
* ``4223`` -- embedded NATS WebSocket listener.
* ``8081`` -- dashboard backend HTTP server (DASHBOARD_PORT). The test
  hits ``/health`` here. Auto-falls back to next free port if 8081 was
  busy at orchestrator boot (D-39); the test asserts the default port
  is reachable on a clean machine.
* ``8088`` -- ``oam ui`` HTTP server. Distinct from 4223 by design.

Every ``mesh.kv.list(...)`` call uses a NATS wildcard suffix (``.>``).
Every ``client._nc.subscribe(...)`` for status pubsub uses ``.*.`` between
fleet_type and ``status`` (single-token wildcard); ``>`` is terminal-only
and would close the connection.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from openagentmesh import AgentMesh
from openagentmesh._local import AGENTMESH_DIR

from demos.wildfire.core.config import DASHBOARD_PORT, MEDEVAC_COUNT
from demos.wildfire.core.contracts import (
    Coords,
    DetectionRecord,
    DispatchOrder,
)
from demos.wildfire.core.keys import DETECTION_PREFIX, FLEET_PREFIX

# Repository root: tests/wildfire/integration/test_phase2_cascade.py -> ROOT.
ROOT = Path(__file__).resolve().parents[3]

# NATS wildcards. Bare prefixes return [] per src/openagentmesh/_context.py:375-405.
DETECTION_WILDCARD = f"{DETECTION_PREFIX}.>"
FLEET_WILDCARD = f"{FLEET_PREFIX}.>"

# oam ui HTTP server port (plan 08 DEFAULT_PORT). Distinct from NATS WS on 4223.
UI_HTTP_PORT = 8088

# Expected catalog entries (Phase 1 + Phase 2: ground.medevac added in 02-04).
EXPECTED_AGENTS = {
    "fire-sim",
    "high-alt.uav",
    "low-alt.drone",
    "low-alt.heli",
    "ground.ffunit",
    "ground.medevac",
}

# 1 uav + 5 drones + 1 heli + 3 ffunits + MEDEVAC_COUNT(3) medevacs = 13.
EXPECTED_FLEET_COUNT = 10 + MEDEVAC_COUNT


pytestmark = pytest.mark.skipif(
    not os.environ.get("OAM_INTEGRATION_TESTS"),
    reason="set OAM_INTEGRATION_TESTS=1 to run multi-process integration tests",
)


def _ensure_ui_built() -> None:
    """Build the admin UI assets if missing; idempotent."""
    index = ROOT / "src" / "openagentmesh" / "_ui_assets" / "index.html"
    if index.exists():
        return
    ui_dir = ROOT / "ui"
    subprocess.run(["corepack", "enable"], check=False)
    subprocess.run(["pnpm", "install"], cwd=ui_dir, check=True)
    subprocess.run(["pnpm", "run", "build"], cwd=ui_dir, check=True)
    assert index.exists(), f"build did not produce {index}"


def _ensure_dashboard_built() -> None:
    """Build the dashboard SPA bundle if missing; idempotent.

    The orchestrator's dashboard child checks for
    ``demos/wildfire/dashboard/dist/index.html`` at startup and exits 2
    if absent (D-36). We build once here so the integration test does not
    depend on out-of-band setup (mirrors ``_ensure_ui_built`` for admin UI).
    """
    index = ROOT / "demos" / "wildfire" / "dashboard" / "dist" / "index.html"
    if index.exists():
        return
    dash_dir = ROOT / "demos" / "wildfire" / "dashboard"
    subprocess.run(["corepack", "enable"], check=False)
    subprocess.run(["pnpm", "install"], cwd=dash_dir, check=True)
    subprocess.run(["pnpm", "run", "build"], cwd=dash_dir, check=True)
    assert index.exists(), f"build did not produce {index}"


def _wipe_state() -> None:
    """Delete stale JetStream state from prior runs (best-effort)."""
    run_data = AGENTMESH_DIR / "run" / "wildfire"
    if run_data.exists():
        shutil.rmtree(run_data, ignore_errors=True)


def _wait_for_url(proc: subprocess.Popen, deadline_s: float = 30.0) -> str:
    """Read orchestrator stdout until it logs the embedded NATS URL.

    Mirrors the helper in ``test_phase1_cascade``. The orchestrator emits
    ``[orchestrator] embedded NATS at nats://127.0.0.1:4222 (ws on :4223)``;
    we parse the URL and return it.
    """
    url_re = re.compile(r"embedded NATS at (nats://[^\s]+)")
    start = time.time()
    out: list[bytes] = []
    while time.time() - start < deadline_s:
        line = proc.stdout.readline() if proc.stdout else b""
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"orchestrator exited early; stdout:\n"
                    f"{b''.join(out).decode(errors='replace')}"
                )
            time.sleep(0.1)
            continue
        out.append(line)
        text = line.decode("utf-8", errors="replace")
        m = url_re.search(text)
        if m:
            return m.group(1)
    raise TimeoutError(
        f"did not see NATS URL within {deadline_s}s; stdout:\n"
        f"{b''.join(out).decode(errors='replace')}"
    )


async def _collect_subject_messages(
    client: AgentMesh, subject: str, *, timeout: float, expected: int = 1
) -> list[bytes]:
    """Side-channel raw NATS sub: collect up to ``expected`` messages on
    ``subject`` for at most ``timeout`` seconds.

    Subject must follow NATS subject grammar: ``*`` matches one token,
    ``>`` is terminal-only. Malformed wildcards (e.g. ``a.>.b``) are
    rejected by the server and close the connection.
    """
    assert client._nc is not None
    collected: list[bytes] = []
    sub = await client._nc.subscribe(subject)
    deadline = time.time() + timeout
    try:
        while time.time() < deadline and len(collected) < expected:
            try:
                msg = await asyncio.wait_for(sub.next_msg(timeout=0.5), timeout=0.6)
                if msg.data:
                    collected.append(msg.data)
            except asyncio.TimeoutError:
                continue
    finally:
        with contextlib.suppress(Exception):
            await sub.unsubscribe()
    return collected


async def test_phase2_cascade(tmp_path: Path) -> None:  # noqa: ARG001 -- pytest fixture
    """End-to-end Phase 2 cascade.

    Mirrors ``test_phase1_cascade`` and adds:

    a. catalog includes ``ground.medevac``,
    b. fleet count rises to 10 + MEDEVAC_COUNT,
    c. heli + medevac warm dispatch via ``mesh.call`` returns
       ``accepted=True`` and a status pubsub frame appears on
       ``mesh.action.{fleet_type}.*.status``,
    d. dashboard ``/health`` returns 200 with ``mesh_instance_id``.
    """
    _ensure_ui_built()
    _ensure_dashboard_built()
    _wipe_state()

    env = {**os.environ}

    # 1. Boot orchestrator subprocess.
    orch = subprocess.Popen(  # noqa: S603 -- argv is constants
        [sys.executable, "-m", "demos.wildfire"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        # 2. Wait for NATS readiness signal in stdout.
        url = _wait_for_url(orch, deadline_s=30.0)

        # 3. Give children a moment to register and start heartbeating.
        #    Phase 2 has 3 extra medevac processes + the dashboard backend,
        #    so a slightly longer buffer than Phase 1's 3s.
        await asyncio.sleep(4.0)

        # 4. Side-channel client.
        client = AgentMesh(url)
        async with client:
            # 4a. Catalog populates with all 6 Phase 1+2 agents.
            deadline = time.time() + 15.0
            catalog = await client.catalog()
            names = {e.name for e in catalog}
            while time.time() < deadline and not EXPECTED_AGENTS <= names:
                await asyncio.sleep(0.5)
                catalog = await client.catalog()
                names = {e.name for e in catalog}
            assert EXPECTED_AGENTS <= names, (
                f"missing agents in catalog: have={names}, "
                f"expected_subset={EXPECTED_AGENTS}"
            )

            # 4b. ~13 fleet heartbeat keys.
            deadline = time.time() + 15.0
            fleet_entries = await client.kv.list(FLEET_WILDCARD)
            while time.time() < deadline and len(fleet_entries) < EXPECTED_FLEET_COUNT:
                await asyncio.sleep(0.5)
                fleet_entries = await client.kv.list(FLEET_WILDCARD)
            assert len(fleet_entries) >= EXPECTED_FLEET_COUNT, (
                f"expected >= {EXPECTED_FLEET_COUNT} fleet heartbeat entries, "
                f"got {len(fleet_entries)}: keys={[e.key for e in fleet_entries]}"
            )

            # 4c. Drive the cascade: spawn a hot cell at the origin.
            spawn = subprocess.run(  # noqa: S603 -- argv is constants
                [sys.executable, "-m", "demos.wildfire.world.spawn", "0", "0", "600"],
                cwd=str(ROOT),
                env={**env, "NATS_URL": url},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30.0,
            )
            assert spawn.returncode == 0, (
                f"spawn failed (rc={spawn.returncode}): "
                f"stdout={spawn.stdout.decode(errors='replace')} "
                f"stderr={spawn.stderr.decode(errors='replace')}"
            )

            surveyed = False
            deadline = time.time() + 60.0
            while time.time() < deadline:
                entries = await client.kv.list(DETECTION_WILDCARD)
                for e in entries:
                    try:
                        rec = DetectionRecord.model_validate_json(e.value)
                    except Exception:
                        continue
                    if rec.state == "surveyed":
                        surveyed = True
                        break
                if surveyed:
                    break
                await asyncio.sleep(1.0)
            if not surveyed:
                detections = await client.kv.list(DETECTION_WILDCARD)
                fleet = await client.kv.list(FLEET_WILDCARD)
                pytest.fail(
                    f"no detection reached state=surveyed within 60s. "
                    f"detections={[(e.key, e.value[:120]) for e in detections]}; "
                    f"fleet_keys={[e.key for e in fleet]}"
                )

            # 4d. Heli warm dispatch via mesh.call. Subscribe to status BEFORE
            #     dispatching so we don't miss the initial 'dispatched' frame.
            heli_status_task = asyncio.create_task(
                _collect_subject_messages(
                    client, "mesh.action.heli.*.status", timeout=20.0, expected=1,
                )
            )
            await asyncio.sleep(0.1)  # let the sub bind before publishing
            heli_ack = await client.call(
                "low-alt.heli",
                DispatchOrder(
                    order_id=uuid.uuid4().hex,
                    target_coords=Coords(x=1.0, y=1.0),
                    priority="med",
                    operator_id="test-op",
                    issued_at=time.time(),
                ),
                timeout=10.0,
            )
            assert heli_ack.get("accepted") is True, f"heli rejected: {heli_ack}"
            assert heli_ack.get("instance_id"), f"heli ack has no instance_id: {heli_ack}"
            heli_messages = await heli_status_task
            assert heli_messages, "no HeliStatus messages within 20s of dispatch"

            # 4e. Medevac warm dispatch via mesh.call. Same pattern.
            medevac_status_task = asyncio.create_task(
                _collect_subject_messages(
                    client, "mesh.action.medevac.*.status", timeout=20.0, expected=1,
                )
            )
            await asyncio.sleep(0.1)
            medevac_ack = await client.call(
                "ground.medevac",
                DispatchOrder(
                    order_id=uuid.uuid4().hex,
                    target_coords=Coords(x=1.0, y=-1.0),
                    priority="high",
                    operator_id="test-op",
                    issued_at=time.time(),
                    persons_estimated=1,
                ),
                timeout=10.0,
            )
            assert medevac_ack.get("accepted") is True, f"medevac rejected: {medevac_ack}"
            assert medevac_ack.get("instance_id"), f"medevac ack: {medevac_ack}"
            medevac_messages = await medevac_status_task
            assert medevac_messages, "no MedevacStatus messages within 20s of dispatch"

        # 5. Dashboard /health smoke (regression net for D-37).
        health_resp = urllib.request.urlopen(  # noqa: S310 -- localhost
            f"http://127.0.0.1:{DASHBOARD_PORT}/health",
            timeout=5,
        )
        health = json.loads(health_resp.read().decode())
        assert health.get("status") == "ok", f"dashboard /health: {health}"
        assert "mesh_instance_id" in health, (
            f"dashboard /health missing mesh_instance_id: {health}"
        )

        # 6. Admin UI /config.json (regression: 02-08 EventFeed didn't break it).
        cfg_resp = urllib.request.urlopen(  # noqa: S310 -- localhost
            f"http://127.0.0.1:{UI_HTTP_PORT}/config.json",
            timeout=5,
        )
        cfg = json.loads(cfg_resp.read().decode())
        assert "nats_ws_url" in cfg, f"unexpected admin /config.json payload: {cfg}"

    finally:
        # 7. Tear down: SIGTERM the orchestrator process group, escalate to
        #    SIGKILL on timeout. We use the PG so the entire fleet tree dies
        #    (T-02-09-03 mitigation: no orphans).
        try:
            os.killpg(os.getpgid(orch.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            orch.terminate()
        try:
            orch.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(orch.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                orch.kill()
            orch.wait()
