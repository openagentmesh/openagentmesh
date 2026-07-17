# DRAFT — Show HN post

> **Status: draft, unpublished. Needs Luca's review; posting to HN is his explicit go.**
> Written by the roadmap executor (Stage 2, item 3). HN conventions applied: plain
> first-person text, no marketing tone, technical detail up front, honest limitations,
> invitation to critique. Title kept under 80 characters. The first comment (posted by
> the author immediately after submitting) is included below, a common HN pattern for
> extra context that would bloat the main text.

---

## Title

Show HN: OpenAgentMesh – a service mesh for AI agents, built on NATS

*(alternates, pick one:)*

- Show HN: OpenAgentMesh – typed contracts and runtime discovery for AI agents
- Show HN: An agent mesh – MCP for tools, A2A for federation, OAM for inside

## URL

https://github.com/openagentmesh/openagentmesh

## Text

I kept running into the same problem building multi-agent systems: every framework
assumes all your agents live in one process, importing each other directly. Add an
agent, update every caller. Different teams, different deploy schedules? You end up
building ad-hoc service discovery on top of HTTP, again.

OpenAgentMesh is a protocol + Python SDK that treats agents like services in a service
mesh. Agents register on a shared NATS bus, publish typed contracts (JSON Schema,
generated from type hints via Pydantic), and discover/call each other at runtime by
name. No hardcoded addresses, no imports across teams.

An agent is an async function:

    mesh = AgentMesh()

    @mesh.agent(AgentSpec(name="echo", description="Echoes a message back."))
    async def echo(req: str) -> str:
        return f"Echo: {req}"

    mesh.run()

The decorator infers the contract from the function shape: return type vs. yield
decides request/reply vs. streaming; the annotations become input/output schemas.
Any other process can then do `await mesh.call("echo", "hello")` or find it via
`mesh.catalog()` (~25 tokens per agent, so an LLM can scan a large catalog and pick
one without blowing its context).

Why NATS: one binary gives pub/sub, request/reply, load balancing (queue groups), KV
(the registry), and object storage. Run N instances of an agent and requests balance
across them with zero config. `oam mesh up` starts everything locally.

It's positioned between the two protocol standards rather than against them: MCP
connects an LLM to tools, A2A federates agents across orgs. OAM is the fabric inside.
There's a built-in MCP bridge (`claude mcp add mesh -- oam mcp serve` exposes opted-in
mesh agents to any MCP client) and contracts are a superset of A2A Agent Cards, so
projecting outward is a method call.

What it deliberately does NOT do: no LLM gateway, no prompt management, no memory, no
orchestration. The handler body is yours (LangGraph, CrewAI, plain Python, whatever).
OAM owns transport, contracts, and discovery only.

Honest limitations: it's young. Python SDK is the mature path; the TypeScript SDK is
early. Auth/multi-tenant hardening is in progress (tracked in ADRs in the repo).
Protocol docs are published if you want to implement a client in another language.

MIT licensed. I'd genuinely value feedback on the protocol design, especially from
people who've run NATS or service meshes in production.

## Prepared first comment (post immediately after submitting)

A bit more technical detail for anyone curious:

- Five handler patterns inferred from function shape: Responder (takes input,
  returns), Streamer (takes input, yields), Trigger (no input, returns), Publisher
  (no input, yields), Watcher (background task). No capability flags anywhere.
- Discovery is two-tier on purpose: `catalog()` returns name/description/tags per
  agent (cheap, LLM-scannable), `contract()` fetches full JSON Schemas for the one
  agent you picked. Scales to ~500 agents with no vector DB.
- The registry is NATS KV with compare-and-swap on catalog updates; concurrent
  registrations retry read-modify-write.
- Validation runs at the mesh boundary (Pydantic v2); malformed requests are
  rejected with a typed error envelope before reaching your handler.
- Wire format is documented (subjects + JSON envelope), so any NATS client in any
  language can participate without the SDK.

Happy to answer anything about design trade-offs, especially "why not just gRPC/HTTP"
(short answer: discovery, queue groups, and pub/sub come free with the bus; with HTTP
you rebuild all three).
