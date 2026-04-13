# OAM and MCP

OpenAgentMesh does not replace MCP. It complements it.

MCP is the standard for connecting LLMs to tools. OAM supports it directly -- any agent contract can be projected into the tool format your LLM expects:

```python
from openagentmesh import AgentMesh

mesh = AgentMesh("nats://localhost:4222")
contract = await mesh.contract("summarizer")

# Use with Anthropic's Claude
anthropic_tool = contract.to_anthropic_tool()

# Use with OpenAI
openai_tool = contract.to_openai_tool()

# Framework-agnostic format
generic_tool = contract.to_generic_tool()
```

So where does OAM add value? In three areas where MCP alone runs into friction at enterprise scale.

## When MCP is "too much": context bloat

MCP works well with a handful of tools. In an enterprise with hundreds of tools across dozens of teams, loading every tool specification into the LLM's context makes tool selection brittle. The model sees too many options and picks the wrong one -- or the context window fills up before the conversation starts.

OAM solves this with **two-tier discovery**:

```python
# Tier 1: lightweight catalog (~20-30 tokens per agent)
catalog = await mesh.catalog(channel="nlp")
# Returns: name, description, tags -- enough for an LLM to pick the right agent

# Tier 2: full contract (only for the agent you need)
contract = await mesh.contract("summarizer")
# Returns: complete JSON Schemas, SLA metadata, error schemas
```

An LLM can scan a catalog of 500 agents in a single context window, select the right one, then fetch only that agent's full schema. No vector database needed.

## When MCP is "not enough": patterns beyond request/reply

MCP is client-to-tool: a client calls one tool at a time, with streamed responses over SSE or stdio. OAM supports three agent-to-agent interaction patterns:

```python
# 1. Sync request/reply (like MCP)
result = await mesh.call("summarizer", payload, timeout=30.0)

# 2. Async callback -- fire and continue working
await mesh.send("summarizer", payload, reply_to="mesh.results.abc")

# 3. Pub/sub -- fan-out events to any number of listeners
# (agents can emit events that other agents subscribe to)
```

Pub/sub and async callbacks enable patterns that MCP doesn't address: event-driven workflows, pipeline fan-out, and long-running tasks with callback notification.

## Enterprise discovery

In enterprise settings, a new MCP server from Team A requires every consumer to manually configure it. Someone has to communicate that the server exists, share the connection details, and every consumer team has to update their MCP client configuration.

With OAM, discovery is automatic:

```python
# Team A registers an agent -- no announcement needed
@mesh.agent(name="risk-scorer", channel="finance", description="...", tags=["risk"])
async def score_risk(req: RiskInput) -> RiskOutput:
    ...

# Team B discovers it at runtime -- no configuration needed
catalog = await mesh.catalog(tags=["risk"])
# The new agent appears immediately
```

No Slack messages. No configuration PRs. No "did you add the new MCP server?" conversations.

## The relationship

| Concern | MCP | OAM |
|---------|-----|-----|
| LLM-to-tool invocation | Native | Via `to_anthropic_tool()` / `to_openai_tool()` |
| Tool discovery | Manual configuration | Automatic runtime discovery |
| Interaction model | Client-initiated, single tool, streamed response | Agent-to-agent: sync, async callback, pub/sub |
| Load balancing | Not supported | NATS queue groups (built-in) |
| Cross-team discovery | Manual setup per consumer | Automatic via shared mesh |
| Context efficiency | Full schema per tool | Two-tier: catalog then contract |

!!! tip "Use both"
    OAM agents can be projected as MCP tools. Use OAM for the internal fabric -- discovery, routing, validation -- and project to MCP format at the LLM boundary.

For how OAM relates to Google's A2A protocol, see [OAM and A2A](oam-and-a2a.md).
