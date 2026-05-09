"""Phase 1 cascade integration test (D-21).

Boots the full Phase 1 demo via subprocess (``python -m demos.wildfire``),
runs the spawn CLI to inject a hot cell, and asserts the cascade reaches
``state="surveyed"`` within a 60 s timeout. Also verifies the admin UI
HTTP server (``oam ui`` on port 8088) is up by hitting ``/config.json``
and ``/``.

The test is gated behind ``OAM_INTEGRATION_TESTS=1`` because it boots ~12
subprocesses, takes 60-90 s end-to-end, and requires ``pnpm`` available
locally to build the admin UI assets on first run. Manual invocation:

    OAM_INTEGRATION_TESTS=1 uv run pytest tests/wildfire/integration -x -q -s

Port mental model:

* ``4222`` -- embedded NATS standard listener (the test connects its
  side-channel client here).
* ``4223`` -- embedded NATS WebSocket listener (browser uses this; not
  hit by this test).
* ``8088`` -- ``oam ui`` HTTP server. The test hits ``/config.json`` and
  ``/`` here. Distinct from 4223 by design (plan 08 sets
  ``DEFAULT_PORT = 8088`` for ``oam ui`` specifically to remove the
  collision).

Every ``mesh.kv.list(...)`` call uses a NATS wildcard suffix (``.>``).
Bare prefixes return ``[]`` per ``src/openagentmesh/_context.py:375-405``.
"""
from __future__ import annotations

import asyncio
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
from pathlib import Path

import pytest

from openagentmesh import AgentMesh
from openagentmesh._local import AGENTMESH_DIR
from demos.wildfire.core.contracts import DetectionRecord
from demos.wildfire.core.keys import DETECTION_PREFIX, FLEET_PREFIX

# Repository root: tests/wildfire/integration/test_phase1_cascade.py -> ROOT.
ROOT = Path(__file__).resolve().parents[3]

# NATS wildcards. Bare prefixes return [] per src/openagentmesh/_context.py:375-405.
DETECTION_WILDCARD = f"{DETECTION_PREFIX}.>"
FLEET_WILDCARD = f"{FLEET_PREFIX}.>"

# oam ui HTTP server port (plan 08 DEFAULT_PORT). Distinct from NATS WS on 4223.
UI_HTTP_PORT = 8088

# Expected catalog entries.
EXPECTED_AGENTS = {
    "fire-sim",
    "high-alt.uav",
    "low-alt.drone",
    "low-alt.heli",
    "ground.ffunit",
}

# 1 uav + 5 drones + 1 heli + 3 ffunits = 10. fire-sim has no fleet record per
# plan 04 SUMMARY.
EXPECTED_FLEET_COUNT = 10


pytestmark = pytest.mark.skipif(
    not os.environ.get("OAM_INTEGRATION_TESTS"),
    reason="set OAM_INTEGRATION_TESTS=1 to run multi-process integration tests",
)


def _ensure_ui_built() -> None:
    """Build the admin UI assets if missing; idempotent.

    The orchestrator's ``oam ui`` child checks for
    ``src/openagentmesh/_ui_assets/index.html`` at startup and exits non-zero
    if absent. We build once here so the integration test does not depend on
    out-of-band setup.
    """
    index = ROOT / "src" / "openagentmesh" / "_ui_assets" / "index.html"
    if index.exists():
        return
    ui_dir = ROOT / "ui"
    # corepack enable may fail (already enabled or non-corepack node); fine.
    subprocess.run(["corepack", "enable"], check=False)
    subprocess.run(["pnpm", "install"], cwd=ui_dir, check=True)
    subprocess.run(["pnpm", "run", "build"], cwd=ui_dir, check=True)
    assert index.exists(), f"build did not produce {index}"


def _ensure_dashboard_built() -> None:
    """Build the dashboard SPA bundle if missing; idempotent.

    The Phase 2 orchestrator (plan 02-09) unconditionally spawns
    ``python -m demos.wildfire.dashboard``. If ``dist/index.html`` is
    missing, the dashboard exits 2 with a "run pnpm run build" message
    on stderr, which would spam this Phase 1 test's stdout via the
    ``[dash]`` log multiplexer. Building once up front avoids that
    noise; nothing in Phase 1's assertions touches the dashboard.
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

    The orchestrator emits a line like::

        [orchestrator] embedded NATS at nats://127.0.0.1:4222 (ws on :4223)

    We parse the URL from the first match and return it. Raises if the
    process exits early or the line never appears.
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


async def test_phase1_cascade(tmp_path: Path) -> None:  # noqa: ARG001 -- pytest fixture
    """End-to-end Phase 1 cascade: boot, spawn fire, observe surveyed detection."""
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
        await asyncio.sleep(3.0)

        # 4. Drive the cascade: spawn a hot cell at the origin.
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

        # 5. Side-channel client to poll KV / catalog.
        client = AgentMesh(url)
        async with client:
            # 5a. Wait for catalog to populate with all 5 Phase 1 agents.
            deadline = time.time() + 10.0
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

            # 5b. Wait for ~10 fleet heartbeat keys (1+5+1+3).
            deadline = time.time() + 10.0
            fleet_entries = await client.kv.list(FLEET_WILDCARD)
            while time.time() < deadline and len(fleet_entries) < EXPECTED_FLEET_COUNT:
                await asyncio.sleep(0.5)
                fleet_entries = await client.kv.list(FLEET_WILDCARD)
            assert len(fleet_entries) >= EXPECTED_FLEET_COUNT, (
                f"expected >= {EXPECTED_FLEET_COUNT} fleet heartbeat entries, "
                f"got {len(fleet_entries)}: keys={[e.key for e in fleet_entries]}"
            )

            # 5c. Poll for at least one DetectionRecord reaching state=surveyed.
            #     UAV must trip threshold -> drone must CAS-claim -> drone must
            #     simulate travel + survey -> rewrite record with state=surveyed.
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
                # Diagnostic dump for triage.
                detections = await client.kv.list(DETECTION_WILDCARD)
                fleet = await client.kv.list(FLEET_WILDCARD)
                pytest.fail(
                    f"no detection reached state=surveyed within 60s. "
                    f"detections={[(e.key, e.value[:120]) for e in detections]}; "
                    f"fleet_keys={[e.key for e in fleet]}"
                )

        # 6. Admin UI HTTP probe.
        #    Hits http://127.0.0.1:8088/config.json (HTTP), NOT
        #    http://127.0.0.1:4223 (which is the NATS WebSocket listener
        #    and would be answered by the NATS server, not by oam ui).
        cfg_resp = urllib.request.urlopen(  # noqa: S310 -- localhost
            f"http://127.0.0.1:{UI_HTTP_PORT}/config.json",
            timeout=5,
        )
        cfg = json.loads(cfg_resp.read().decode())
        assert "nats_ws_url" in cfg, f"unexpected /config.json payload: {cfg}"

        index_resp = urllib.request.urlopen(  # noqa: S310 -- localhost
            f"http://127.0.0.1:{UI_HTTP_PORT}/",
            timeout=5,
        )
        index_body = index_resp.read().decode()
        body_lower = index_body.lower()
        assert "<html" in body_lower, f"unexpected /: not HTML, got {index_body[:200]!r}"
        # The Vite-bundled SPA should mount on a #root element. We accept the
        # marker liberally (case-insensitive) because exact title may evolve.
        assert ("openagentmesh" in body_lower or "id=\"root\"" in body_lower or "id='root'" in body_lower), (
            f"unexpected /: missing OpenAgentMesh / root marker, "
            f"got {index_body[:300]!r}"
        )
    finally:
        # 7. Tear down: SIGTERM the orchestrator process group, escalate to
        #    SIGKILL on timeout. We use the PG so the entire fleet tree dies.
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
