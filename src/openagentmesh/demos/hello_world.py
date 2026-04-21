"""Register a greeting agent on the mesh, call it, then stay open for interaction."""

import asyncio
import signal
import sys
from pathlib import Path
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class Greeting(BaseModel):
    name: str

class Response(BaseModel):
    message: str


def _step(icon: str, text: str) -> None:
    print(f"  {icon} {text}")


async def main(mesh: AgentMesh) -> None:
    print()
    _step("\u2714", f"Connected to mesh at {mesh._url}")

    
    @mesh.agent(AgentSpec(name="greeter", description="Returns a greeting for the given name"))
    async def greeter(req: Greeting) -> Response:
        return Response(message=f"Hello, {req.name}!")
    _step("\u2714", "Agent 'greeter' registered (handler shape: Responder)")

    @mesh.agent(AgentSpec(name="counter", description="Counts from a given number for ten times"))
    async def counter(start: int) -> int:
        for i in range(start, start + 10):
            await asyncio.sleep(1)
            yield i
    _step("\u2714", "Agent 'counter' registered (handler shape: Streamer)")

    _step("\u2714", "Agents registered")
    _step("\u2714", f"Catalog updated ({len(await mesh.catalog())} agents)")

    print("\n  Calling greeter({\"name\": \"World\"})...")
    result = await mesh.call("greeter", Greeting(name="World"))
    _step("\u2714", f"Response: {result['message']}")

    if not sys.stdout.isatty():
        return

    # Write .oam-url so other terminals can discover this mesh
    url_file = Path.cwd() / ".oam-url"
    url_file.write_text(f"{mesh._url}\n")

    print("\n  Mesh is live. In another terminal, try:")
    print(f"    oam mesh catalog")
    print(f"    oam agent contract greeter")
    print(f"    oam agent call greeter '{{\"name\": \"Alice\"}}'")
    print(f"    oam agent stream counter '0'")
    print("\n  Press Ctrl+C to stop.\n")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    if url_file.exists():
        url_file.unlink()
    print("\n  Mesh stopped.")
