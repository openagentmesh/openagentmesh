"""Mesh URL resolution for the CLI (ADR-0033, extended by ADR-0038).

Precedence: --url flag > OAM_URL env > .oam-url file (walked up from cwd)
> default nats://localhost:4222.

`.oam-url` accepts two forms: a legacy bare URL line, or a small TOML with
`url` and optional `creds` fields (ADR-0038). Parsing lives in
`openagentmesh._auth` and is shared with the SDK's credential resolution.
"""

from __future__ import annotations

import os
from pathlib import Path

from openagentmesh._auth import OAM_URL_FILE, find_target_file, parse_target_file

DEFAULT_URL = "nats://localhost:4222"
ENV_VAR = "OAM_URL"

__all__ = ["DEFAULT_URL", "ENV_VAR", "OAM_URL_FILE", "resolve_url", "write_url_file"]


def resolve_url(flag: str | None, *, cwd: Path | None = None) -> str:
    """Resolve the mesh URL using the CLI precedence rules."""
    if flag:
        return flag

    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return env_value

    start = cwd if cwd is not None else Path.cwd()
    file_path = find_target_file(start)
    if file_path is not None:
        target = parse_target_file(file_path)
        if target.url:
            return target.url

    return DEFAULT_URL


def write_url_file(url: str, *, creds: str | None = None, cwd: Path | None = None) -> Path:
    """Write `.oam-url` in the given directory (defaults to cwd).

    Bare URL without credentials (legacy form); TOML once `creds` is present.
    """
    target_dir = cwd if cwd is not None else Path.cwd()
    target = target_dir / OAM_URL_FILE
    if creds is None:
        target.write_text(f"{url}\n")
    else:
        target.write_text(f'url = "{url}"\ncreds = "{creds}"\n')
    return target
