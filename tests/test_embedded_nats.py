"""EmbeddedNats startup: auto-port collision retry.

`_free_port()` is check-then-use: the probed port can be taken by anything
else between the probe and nats-server binding it (seen as a real CI flake —
`[FTL] ... bind: address already in use`). Auto-selected ports must be
re-picked and the boot retried; the failure must still surface when retries
are exhausted.
"""

import socket

import pytest

from openagentmesh import _local
from openagentmesh._local import EmbeddedNats


class TestPortCollisionRetry:
    async def test_retries_when_free_port_choice_collides(self, monkeypatch):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        occupied = blocker.getsockname()[1]

        real_free_port = _local._free_port
        calls = {"n": 0}

        def racy_free_port() -> int:
            # First pick (attempt 1's client port) lands on the occupied
            # port, as if another process grabbed it after the probe.
            calls["n"] += 1
            if calls["n"] == 1:
                return occupied
            return real_free_port()

        monkeypatch.setattr(_local, "_free_port", racy_free_port)

        embedded = EmbeddedNats()
        try:
            await embedded.start()
            assert embedded.port != occupied
            assert embedded.ws_port != occupied
            assert calls["n"] >= 3  # attempt 1 (collided) + attempt 2's re-picks
        finally:
            await embedded.stop()
            blocker.close()

    async def test_raises_when_retries_exhausted(self, monkeypatch):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        occupied = blocker.getsockname()[1]

        monkeypatch.setattr(_local, "_free_port", lambda: occupied)

        embedded = EmbeddedNats()
        try:
            with pytest.raises(RuntimeError, match="address already in use"):
                await embedded.start()
        finally:
            blocker.close()
