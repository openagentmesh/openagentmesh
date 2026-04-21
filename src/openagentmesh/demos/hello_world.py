"""Register a greeting agent on the mesh, call it, then stay open for interaction."""

import asyncio
import random
import signal
import sys
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field

from openagentmesh import AgentMesh, AgentSpec


class Greeting(BaseModel):
    name: str

class Response(BaseModel):
    message: str

class Ticker(BaseModel):
    symbol: str | None = 'ACME'
    timestamp: datetime = Field(default_factory=datetime.now)
    price: float


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


    @mesh.agent(AgentSpec(name="ticker", description="Shows a ticker symbol and price"))
    async def ticker() -> Ticker:
        while True:
            yield Ticker(price=round(random.uniform(75, 82), 4))
            await asyncio.sleep(1)
    _step("\u2714", "Agent 'ticker' registered (handler shape: Publisher)")

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
    print(f"    oam agent subscribe ticker")
    print("\n  Press Ctrl+C to stop.\n")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    if url_file.exists():
        url_file.unlink()
    print("\n  Mesh stopped.")
