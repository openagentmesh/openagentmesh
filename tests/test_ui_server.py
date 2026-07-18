"""ADR-0056 wave 1: websocket listener + `oam ui` static server."""

from __future__ import annotations

import asyncio
import json
import socket
import urllib.request

import pytest

from openagentmesh._local import EmbeddedNats, render_mesh_server_conf
from openagentmesh.cli.ui import UIAssetsMissing, UIServer, derive_ws_url

pytestmark = pytest.mark.asyncio


async def _ws_handshake_status(host: str, port: int) -> str:
    """Raw HTTP upgrade against a NATS websocket listener; return the status line."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(
            b"GET / HTTP/1.1\r\n"
            b"Host: %b:%d\r\n"
            b"Connection: Upgrade\r\n"
            b"Upgrade: websocket\r\n"
            b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            b"Sec-WebSocket-Version: 13\r\n"
            b"\r\n" % (host.encode(), port)
        )
        await writer.drain()
        status = await asyncio.wait_for(reader.readline(), timeout=5)
        return status.decode()
    finally:
        writer.close()


class TestWebsocketListener:
    def test_conf_includes_websocket_block(self, tmp_path):
        conf = render_mesh_server_conf(
            port=4222, store_dir=tmp_path, sys_password="x", ws_port=4223
        )
        assert "websocket" in conf
        assert "4223" in conf
        assert "no_tls" in conf

    def test_conf_without_ws_port_has_no_websocket_block(self, tmp_path):
        conf = render_mesh_server_conf(port=4222, store_dir=tmp_path, sys_password="x")
        assert "websocket" not in conf

    async def test_embedded_nats_serves_websocket(self):
        embedded = EmbeddedNats()
        await embedded.start()
        try:
            assert embedded.ws_url.startswith("ws://")
            ws_port = int(embedded.ws_url.rsplit(":", 1)[1])
            status = await _ws_handshake_status("127.0.0.1", ws_port)
            assert "101" in status
        finally:
            await embedded.stop()


class TestDeriveWsUrl:
    def test_derives_port_plus_one(self):
        assert derive_ws_url("nats://localhost:4222") == "ws://localhost:4223"

    def test_defaults_missing_port_to_4222(self):
        assert derive_ws_url("nats://mesh.example.com") == "ws://mesh.example.com:4223"


class TestUIServer:
    @pytest.fixture
    def assets_dir(self, tmp_path):
        (tmp_path / "index.html").write_text("<html>OAM Admin UI</html>")
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "app.js").write_text("console.log('oam')")
        return tmp_path

    def test_serves_config_json(self, assets_dir):
        server = UIServer(assets_dir, nats_ws_url="ws://127.0.0.1:4223", port=0)
        server.start()
        try:
            with urllib.request.urlopen(f"{server.url}/config.json") as resp:
                config = json.loads(resp.read())
            assert config["nats_ws_url"] == "ws://127.0.0.1:4223"
        finally:
            server.stop()

    def test_serves_spa_assets(self, assets_dir):
        server = UIServer(assets_dir, nats_ws_url="ws://127.0.0.1:4223", port=0)
        server.start()
        try:
            with urllib.request.urlopen(f"{server.url}/") as resp:
                assert b"OAM Admin UI" in resp.read()
            with urllib.request.urlopen(f"{server.url}/assets/app.js") as resp:
                assert b"oam" in resp.read()
        finally:
            server.stop()

    def test_falls_back_to_free_port(self, assets_dir):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            taken = blocker.getsockname()[1]

            server = UIServer(assets_dir, nats_ws_url="ws://x:1", port=taken)
            server.start()
            try:
                assert server.port != taken
                with urllib.request.urlopen(f"{server.url}/config.json") as resp:
                    assert resp.status == 200
            finally:
                server.stop()

    def test_missing_assets_raises(self, tmp_path):
        with pytest.raises(UIAssetsMissing, match="pnpm"):
            UIServer(tmp_path, nats_ws_url="ws://x:1", port=0)
