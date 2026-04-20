"""Register a greeting agent on the mesh and call it."""

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class Greeting(BaseModel):
    name: str


class Response(BaseModel):
    message: str


async def main(mesh: AgentMesh) -> None:
    @mesh.agent(AgentSpec(name="greeter", description="Returns a greeting for the given name"))
    async def greeter(req: Greeting) -> Response:
        return Response(message=f"Hello, {req.name}!")

    result = await mesh.call("greeter", Greeting(name="World"))
    print(f"greeter replied: {result['message']}")
