"""NATS server config writer.

Embedded NATS for the wildfire demo orchestrator (D-04, D-15, ADR-0056 amendment).
Generates a HOCON config file with both the standard NATS listener and a WebSocket
listener so the admin UI browser client (nats.ws) can connect directly to the bus.

Both listeners bind to ``127.0.0.1`` only, per T-01-03-02 mitigation -- the Phase 1
threat model treats the demo as localhost-only.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

HOCON_TEMPLATE = """\
host: "127.0.0.1"
port: {port}
http_port: {http_port}
jetstream {{
    store_dir: "{store_dir}"
}}
websocket {{
    host: "127.0.0.1"
    port: {ws_port}
    no_tls: true
}}
"""


def write_nats_config(
    *,
    port: int,
    ws_port: int,
    http_port: int,
    store_dir: Path,
) -> Path:
    """Write a HOCON NATS config to a tempfile and return its path.

    Args:
        port: Standard NATS listener port (clients).
        ws_port: WebSocket listener port (browser clients via ``nats.ws``).
        http_port: NATS monitoring HTTP endpoint.
        store_dir: JetStream store directory; created if missing.

    Returns:
        Path to a ``.conf`` HOCON file. Caller owns cleanup (delete on shutdown).
    """
    store_dir.mkdir(parents=True, exist_ok=True)
    body = HOCON_TEMPLATE.format(
        port=port,
        http_port=http_port,
        ws_port=ws_port,
        store_dir=str(store_dir).replace('"', '\\"'),
    )
    # The tempfile must outlive this function so the orchestrator can pass its
    # path to ``nats-server -c``; ``delete=False`` plus an explicit ``close()`` is
    # the correct pattern here. ``noqa: SIM115`` -- a context manager would delete
    # the file on exit, which is the opposite of what we want.
    f = tempfile.NamedTemporaryFile(  # noqa: SIM115
        "w",
        suffix=".conf",
        prefix="oam-wildfire-nats-",
        delete=False,
    )
    try:
        f.write(body)
    finally:
        f.close()
    return Path(f.name)
