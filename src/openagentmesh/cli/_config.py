"""Mesh URL resolution for the CLI (ADR-0033).

Precedence: --url flag > OAM_URL env > .oam-url file (walked up from cwd)
> default nats://localhost:4222.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_URL = "nats://localhost:4222"
OAM_URL_FILE = ".oam-url"
ENV_VAR = "OAM_URL"


def _find_url_file(start: Path) -> Path | None:
    current = start.resolve()
    while True:
        candidate = current / OAM_URL_FILE
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def _read_url_file(path: Path) -> str | None:
    content = path.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def resolve_url(flag: str | None, *, cwd: Path | None = None) -> str:
    """Resolve the mesh URL using the CLI precedence rules."""
    if flag:
        return flag

    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return env_value

    start = cwd if cwd is not None else Path.cwd()
    file_path = _find_url_file(start)
    if file_path is not None:
        value = _read_url_file(file_path)
        if value:
            return value

    return DEFAULT_URL


def write_url_file(url: str, *, cwd: Path | None = None) -> Path:
    """Write `url` to `.oam-url` in the given directory (defaults to cwd)."""
    target_dir = cwd if cwd is not None else Path.cwd()
    target = target_dir / OAM_URL_FILE
    target.write_text(f"{url}\n")
    return target
