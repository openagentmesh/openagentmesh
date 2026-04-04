"""Unit tests for NATS binary helpers — no network required."""

import platform
from unittest.mock import patch

import pytest

import agentmesh.nats_server as ns


def _url_for(system: str, machine: str) -> str:
    with patch.object(platform, "system", return_value=system), patch.object(
        platform, "machine", return_value=machine
    ):
        return ns._download_url()


# --- Platform detection ---


def test_download_url_macos_arm64():
    url = _url_for("Darwin", "arm64")
    assert f"v{ns.NATS_VERSION}" in url
    assert "darwin" in url
    assert "arm64" in url
    assert url.endswith(".tar.gz")


def test_download_url_macos_x86_64():
    url = _url_for("Darwin", "x86_64")
    assert "darwin" in url
    assert "amd64" in url


def test_download_url_linux_x86_64():
    url = _url_for("Linux", "x86_64")
    assert "linux" in url
    assert "amd64" in url


def test_download_url_linux_aarch64():
    url = _url_for("Linux", "aarch64")
    assert "linux" in url
    assert "arm64" in url


def test_download_url_unsupported_platform():
    with pytest.raises(RuntimeError, match="Unsupported platform"):
        _url_for("Windows", "x86_64")


def test_download_url_contains_version():
    url = _url_for("Darwin", "arm64")
    assert ns.NATS_VERSION in url
