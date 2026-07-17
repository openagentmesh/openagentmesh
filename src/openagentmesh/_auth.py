"""Credential and TLS resolution for the SDK (ADR-0038).

Resolution order for credentials:

1. Explicit ``creds=`` argument on `AgentMesh`.
2. ``OAM_CREDS`` environment variable.
3. ``creds`` field in a ``.oam-url`` file (TOML form), walked up from cwd;
   relative paths resolve against the file's own directory.
4. None: connect open.

``.oam-url`` is backwards-compatible (ADR-0033): a bare URL line is still
valid; the TOML form adds ``url`` and optional ``creds`` fields.
"""

from __future__ import annotations

import os
import ssl
import tomllib
from dataclasses import dataclass
from pathlib import Path

OAM_URL_FILE = ".oam-url"
CREDS_ENV_VAR = "OAM_CREDS"


@dataclass
class MeshTarget:
    """Parsed contents of a ``.oam-url`` file."""

    url: str | None = None
    creds: str | None = None


def find_target_file(start: Path) -> Path | None:
    """Walk up from `start` to the filesystem root looking for ``.oam-url``."""
    current = start.resolve()
    while True:
        candidate = current / OAM_URL_FILE
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def parse_target_file(path: Path) -> MeshTarget:
    """Parse ``.oam-url``: TOML with url/creds fields, or a legacy bare URL."""
    content = path.read_text()
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        data = None

    if isinstance(data, dict) and ("url" in data or "creds" in data):
        url = data.get("url")
        creds = data.get("creds")
        if creds is not None:
            creds_path = Path(creds)
            if not creds_path.is_absolute():
                creds_path = path.parent / creds_path
            creds = str(creds_path)
        return MeshTarget(url=url if isinstance(url, str) else None, creds=creds)

    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return MeshTarget(url=stripped)
    return MeshTarget()


def resolve_creds(explicit: str | None, *, cwd: Path | None = None) -> str | None:
    """Resolve a credentials file path using the ADR-0038 precedence rules."""
    if explicit:
        return explicit

    env_value = os.environ.get(CREDS_ENV_VAR)
    if env_value:
        return env_value

    start = cwd if cwd is not None else Path.cwd()
    target_file = find_target_file(start)
    if target_file is not None:
        return parse_target_file(target_file).creds

    return None


_AUTH_ERROR_MARKERS = (
    "authorization violation",
    "authentication",
    "permissions violation",
    "user authentication expired",
)


def is_auth_error(e: Exception) -> bool:
    """Whether a NATS error is an auth/permission rejection (ADR-0038)."""
    text = str(e).lower()
    return any(marker in text for marker in _AUTH_ERROR_MARKERS)


def build_tls_context(
    *,
    tls_cert: str | None = None,
    tls_key: str | None = None,
    tls_ca: str | None = None,
) -> ssl.SSLContext | None:
    """Build an SSL context from mTLS parameters, or None if none are set."""
    if not (tls_cert or tls_key or tls_ca):
        return None

    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    if tls_ca:
        context.load_verify_locations(cafile=tls_ca)
    if tls_cert and tls_key:
        context.load_cert_chain(certfile=tls_cert, keyfile=tls_key)
    return context
