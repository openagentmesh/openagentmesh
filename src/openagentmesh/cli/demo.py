"""`oam demo` command: run the hello-world demo (ADR-0041)."""

from __future__ import annotations

import asyncio

from .._mesh import AgentMesh
from ..demos import hello_world


def demo() -> None:
    """Start a local mesh with sample agents for interactive exploration."""

    async def _run() -> None:
        async with AgentMesh.local() as mesh:
            await hello_world.main(mesh)

    asyncio.run(_run())
