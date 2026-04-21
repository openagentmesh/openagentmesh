"""Output formatting helpers for the CLI."""

from __future__ import annotations

import json
import sys
from typing import Any


def banner() -> str:
    """Startup banner with mesh art, block-letter OAM, name, and version."""
    try:
        from importlib.metadata import version as _v
        ver = _v("openagentmesh")
    except Exception:
        ver = "dev"

    if not sys.stdout.isatty():
        return f"\n  Open Agent Mesh v{ver}\n"

    C = "\033[36m"
    B = "\033[1m"
    D = "\033[2m"
    R = "\033[0m"

    return "\n".join([
        "",
        f"  {C}● ━━ ● ━━ ●{R}     {B} ███   ███  █   █{R}",
        f"  {C}┃ ╲  ┃  ╱ ┃{R}     {B}█   █ █   █ ██ ██{R}",
        f"  {C}● ━━ ◉ ━━ ●{R}     {B}█   █ █████ █ █ █{R}",
        f"  {C}┃ ╱  ┃  ╲ ┃{R}     {B}█   █ █   █ █   █{R}",
        f"  {C}● ━━ ● ━━ ●{R}     {B} ███  █   █ █   █{R}",
        "",
        f"  {B}Open Agent Mesh{R}  {D}v{ver}{R}",
        f"  {D}The fabric for multi-agent systems{R}",
        "",
    ])


def as_json(obj: Any) -> str:
    """Deterministic JSON output. Pydantic-friendly via model_dump()."""
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    elif isinstance(obj, list) and obj and hasattr(obj[0], "model_dump"):
        obj = [item.model_dump(mode="json") for item in obj]
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


def table(rows: list[list[str]], headers: list[str]) -> str:
    """Plain text table with left-aligned columns and space padding."""
    if not rows:
        return "  ".join(headers) + "\n(empty)"

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    lines = [fmt(headers)]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)
