# DRAFT — launch blog post

> **Status: draft, unpublished. Needs Luca's review before posting anywhere.**
> Written by the roadmap executor (Stage 2, item 3). Every technical claim below is
> demoable on current main: the MCP bridge command, the echo sample, two-tier discovery,
> and queue-group scaling all have passing tests behind them. Nothing here references
> the wildfire demo video (not yet recorded) or the docs URL (pending decision).
> Suggested venues: personal blog / project site, cross-posted to dev.to or Medium.

---

# The Wire, Not the Workflow: Why I Built an Agent Mesh

Everyone building with AI agents right now is building cars. Faster cars, smarter cars, cars that can plan their own routes and refuel themselves mid-journey. The frameworks keep getting better, and honestly, some of them are excellent. But let me ask you a question: have you ever tried to get thirty cars from ten different manufacturers to coordinate a delivery across a city that has no roads?

That is the state of multi-agent systems today. We have remarkable vehicles. We have almost no infrastructure.

I want to show you what I think the roads should look like. But first, let me convince you that the problem is real.

## The coupling problem

Here is how most multi-agent systems are wired together today:

```python
from team_a import summarizer
from team_b import translator
from team_c import sentiment_analyzer

result = await summarizer.invoke(text)
```

Every consumer hardcodes every dependency. Add a new agent, and you are updating every caller that needs to know about it. Remove one, and consumers break, sometimes silently, sometimes at 2 a.m. Scale this past a single team and coordination itself becomes the bottleneck: the Slack messages, the configuration PRs, the "did you add the new server?" conversations.

Don't get me wrong: for a demo, or a single-team project, this is fine. Direct imports are simple and simple is good. The pain starts exactly where the interesting systems start, when agents are built by different people, deployed on different schedules, and need to find each other at runtime.

In my experience with industrial system integration, this pattern has a name: point-to-point spaghetti. Manufacturing companies spent two decades untangling it for their software systems. We are now speedrunning the same mistake with agents.

## Roads, not faster cars

Back to the cars. When a city grows, nobody solves its traffic by making individual cars better. You build infrastructure: roads with agreed conventions, signage that every driver can read, intersections that arbitrate who goes first, and a map that is updated as the city changes. The infrastructure is boring. It is also what makes ten thousand independently operated vehicles into a functioning transport system.

Notice something about good road networks: they do not care what kind of vehicle you drive. A truck, a motorbike, a bus. If you follow the conventions, you participate. The road does not inspect your engine.

That is the layer I kept looking for in the agent ecosystem and could not find. In 2026 we finally have two solid protocol standards: MCP connects LLMs to tools, and A2A federates agents across organizations over HTTP. Both are valuable. But look at where they sit. MCP is the loading dock, where a model picks up its tools. A2A is the international border crossing, with its passports and paperwork. Neither one is the road network *inside* the city, where dozens or hundreds of your own agents need to discover and call each other at runtime without any caller knowing about any provider in advance.

That gap is what OpenAgentMesh fills.

## What it looks like

OpenAgentMesh (OAM) is a protocol and Python SDK for agent-to-agent communication inside an organization. An agent is any async function:

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

@mesh.agent(AgentSpec(name="echo", description="Echoes a message back."))
async def echo(req: str) -> str:
    return f"Echo: {req}"

mesh.run()
```

That is a complete, deployable agent. The decorator inspects the function signature and infers everything else: the input and output JSON Schemas (via Pydantic v2), whether the agent streams (it yields) or replies (it returns), whether it takes input at all. No capability flags, no YAML. The handler shape is the source of truth.

Any other process on the mesh can now find and call it, with no imports and no configuration:

```python
catalog = await mesh.catalog()                     # what's out there right now?
result = await mesh.call("echo", "hello")          # call by name, mesh handles routing
```

Discovery is two-tier by design, and this matters more than it looks. The catalog costs 20 to 30 tokens per agent, compact enough that an LLM can scan hundreds of agents in one context window and pick the right one. Only then do you fetch the full contract, with complete schemas, for the one agent you chose. No vector database, no RAG pipeline, no context bloat.

## Why NATS

Underneath, there is exactly one piece of infrastructure: NATS.[**1**]

I will be honest about how this choice was made: I wanted the roads without hiring a civil engineering department. NATS gives pub/sub, request/reply, load balancing through queue groups, a KV store for the registry, and an object store for shared artifacts. One binary. One connection. Every box that a service mesh needs, already battle-tested in production message systems for years.

The queue groups deserve a special mention. Deploy three instances of the same agent, with zero code changes, and NATS distributes requests across them automatically. Scaling an agent means starting another copy of it. That's it.

And because OAM is protocol-first, the Python SDK is the first implementation, not the boundary. The subjects and message envelopes are documented; any NATS client in any language can participate by following them. A TypeScript SDK already exists in the repo, and the protocol is the contract between them.

## Playing nicely with MCP and A2A

Remember the loading dock and the border crossing? OAM is designed to sit between them, not replace them.

If you use Claude Code or any other MCP client, your whole mesh is two commands away from being a toolbox:

```bash
pip install 'openagentmesh[mcp]'
claude mcp add mesh -- oam mcp serve
```

Agents that opt in are listed and callable as MCP tools, typed schemas included. And every OAM contract is a superset of the A2A Agent Card, so projecting an internal agent to the org boundary is a method call, not a migration.

Use OAM for the internal fabric. Project to MCP at the model boundary and to A2A at the organizational one.

## What OAM is not

This is the part I care most about getting right. OAM owns the wire, the contract, and discovery. Full stop.

It is not an LLM gateway, not a prompt registry, not an agent-memory store, and not a workflow orchestrator. It does not build agents for you. The handler body is your territory: put a LangGraph graph in there, a CrewAI crew, a call through OpenRouter, or fifty lines of deterministic Python. The mesh does not inspect your engine.

This is not to say those platform concerns don't matter. They do. But bundling them into the transport layer is how you get lock-in, and the honest answer is that they can be built *as agents on the mesh* rather than baked into it.

The project is young, and I would rather you hear that from me. The Python SDK is the mature path; the TypeScript SDK is early. Production hardening, auth and failure semantics, is actively in progress and openly tracked in the repo's ADRs. If you need enterprise-grade security guarantees today, watch the repo for another release or two before betting on it.

## Try it

```bash
uv tool install openagentmesh
oam mesh up
oam demo
```

Thirty seconds later you have a local mesh with sample agents you can discover, call, and stream from the CLI. The quickstart in the docs walks through writing your own first agent in under thirty lines.

The interesting multi-agent systems, the ones with agents from different teams cooperating on real work, will be built by people who stopped waiting for a single framework to win. The cars are ready. Come help build the roads.

---

[**1**] NATS is a CNCF-graduated open-source messaging system, originally built for cloud-native service communication. If you have not met it before: think of it as the lightweight, operationally boring cousin of Kafka, with request/reply and KV built in.
