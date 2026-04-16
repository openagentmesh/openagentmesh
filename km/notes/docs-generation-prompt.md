# Documentation Generation Prompt — OpenAgentMesh

**Style model:** Tiangolo (FastAPI). Code-first, progressive disclosure, personality in the prose.

---

## Context

You are writing the user-facing documentation for OpenAgentMesh (OAM), an open-source Python SDK for agent-to-agent communication over NATS. The project is pre-implementation — specs exist in `km/`, existing draft docs in `docs/`, and the structure is defined in `mkdocs.yml`.

Source material (read ALL before writing):
- `km/agentmesh-spec.md` — Protocol specification (authoritative)
- `km/agentmesh-developer-experience.md` — SDK design and DX philosophy
- `km/agentmesh-registry-and-discovery.md` — Registry, channels, catalog, and discovery
- `km/agentmesh-liveness-and-failure.md` — Liveness, failure modes, death notices
- `km/ideas.md` — Unresolved design questions
- `km/notes/Docs structure.md` — Desired outline and positioning notes
- `CLAUDE.md` — Project conventions and contract schema reference
- `docs/**/*.md` — Existing draft documentation

The documentation serves as both:
1. **User-facing docs** for the published site (openagentmesh.dev)
2. **DX contract** that drives test-red-green development — if the docs show an API, the tests should exercise it

---

## Writing Style: The Tiangolo Method

### Core Principles

1. **Code first, explanation second.** Every concept opens with a working code example. The reader sees what it looks like before being told why.

2. **Progressive disclosure.** Start with the simplest possible example. Layer complexity only when the reader needs it. The quickstart has zero configuration. Concepts pages add one idea at a time.

3. **Speak to the reader directly.** "You" not "the user." "Your agent" not "the agent." Conversational but precise.

4. **One idea per section.** If a section covers two ideas, split it. The reader should be able to scan headers and know exactly where to find what they need.

5. **Admonitions for tangents.** Use `!!! tip`, `!!! info`, `!!! warning` for content that enriches but isn't on the critical path. This keeps the main flow clean.

6. **Show, then explain, then show the next thing.** The rhythm is: code block → 1-3 short paragraphs → code block. Never more than 3 paragraphs without code.

7. **No walls of text.** Break long explanations into bullet lists. Use tables for reference material. Diagrams for architecture.

### What NOT to Do

- No "In this section we will learn about..." preambles
- No multi-paragraph introductions before the first code block
- No explaining what Python is or what async means
- No repeating the same concept across pages — link to the canonical page
- No placeholder content or "coming soon" sections — if it's not ready, don't include it
- No excessive admonitions — max 2-3 per page

---

## Page Specifications

### 1. Home (`index.md`) — REWRITE

**Purpose:** Hook the reader in 10 seconds. Show what OAM does before explaining anything.

**Structure:**
- Open with a code block: the simplest possible mesh (2 agents talking, ~15 lines)
- One paragraph: what just happened (agents discovered each other on a shared bus)
- "Why OpenAgentMesh" section: 3-4 short paragraphs on the problem (coupling, discovery, scaling)
- Feature highlight cards (use a grid or list): Discovery, Type Safety, Scale, Protocol-First
- Positioning table: OAM vs MCP vs A2A (keep the existing table, it's good)
- "Next Steps" links: Quickstart, Why OAM, Concepts

**Tone:** Confident, concise. This is the elevator pitch.

### 2. Quickstart (`quickstart.md`) — KEEP + POLISH

**Purpose:** Working system in 5 minutes. Zero to "I see two agents talking."

The existing quickstart is solid. Polish:
- Ensure the opening code block is copy-pasteable and actually runs
- Add brief "What just happened?" callouts after key examples
- Make sure the Reference tables at the bottom stay as a quick cheat sheet

### 3. Why OAM section (`learn/`) — NEW

Four pages that sell the project to technical decision-makers. These are the "Alternatives, Inspiration and Comparisons" of FastAPI.

#### 3a. `learn/index.md` — "Understanding OpenAgentMesh"
Landing page. Brief framing paragraph + links to sub-pages. 

#### 3b. `learn/enterprise-landscape.md` — "The Multi-Agent Landscape"
- The problem: multi-agent systems today are a wiring nightmare
- The landscape: MCP for tools, A2A for federation, what's missing in between
- The gap: no "LAN of agents" — no internal fabric for agent-to-agent within an org
- OAM fills this gap: runtime discovery, typed contracts, zero coupling

#### 3c. `learn/oam-and-mcp.md` — "OAM and MCP"
Draw from `km/notes/Docs structure.md` "Why not just MCP?" section:
- MCP is supported (`to_anthropic_tool()`, `to_openai_tool()`)
- Where MCP falls short: context bloat at scale, no native discovery, client-side setup per tool
- Where OAM complements: catalog for selection, typed validation, pub/sub patterns
- Clear message: not replacing MCP, complementing it

#### 3d. `learn/oam-and-a2a.md` — "OAM and A2A"
- A2A is the cross-org federation standard
- OAM contracts are A2A-compatible superset
- OAM is the internal fabric; A2A is the external bridge
- `to_agent_card(url=...)` for federation boundary

#### 3e. `learn/technology.md` — "Technology Stack"
- Why NATS (already good content in index.md — move and expand)
- Why Pydantic v2 (schema generation, validation)
- Why protocol-first (any language can participate)
- The service mesh analogy (from DX doc section 6)

### 4. Concepts section — KEEP EXISTING + ADD

Existing concept pages (agents, channels, contracts, discovery, invocation) are good. Add:

#### 4a. `concepts/errors.md` — "Error Handling" — NEW
- Error envelope format (from spec)
- Error codes: `validation_error`, `handler_error`, `timeout`, `not_found`, `rate_limited`
- How errors propagate through the mesh
- Code example showing error handling on the consumer side

### 5. Cookbook (`cookbook/`) — NEW (SKELETON)

#### 5a. `cookbook/index.md` — landing page
Brief intro + links to recipes.

#### 5b. `cookbook/multi-process.md` — "Multi-Process Agents"
Expand the existing quickstart "Two Separate Processes" into a proper recipe with:
- Provider and consumer in separate files
- Running them independently
- Showing discovery working across processes

### 6. Getting Help (`help.md`) — NEW

Short page:
- GitHub Issues for bugs/features
- Discord for community discussion
- Enterprise support: openagentmesh@progresslab.it

### 7. `mkdocs.yml` — UPDATE nav

```yaml
nav:
  - Home: index.md
  - Getting Started:
      - Quickstart: quickstart.md
  - Learn:
      - learn/index.md
      - The Multi-Agent Landscape: learn/enterprise-landscape.md
      - OAM and MCP: learn/oam-and-mcp.md
      - OAM and A2A: learn/oam-and-a2a.md
      - Technology Stack: learn/technology.md
  - Concepts:
      - concepts/index.md
      - Agents: concepts/agents.md
      - Channels: concepts/channels.md
      - Contracts: concepts/contracts.md
      - Discovery: concepts/discovery.md
      - Invocation: concepts/invocation.md
      - Error Handling: concepts/errors.md
  - Cookbook:
      - cookbook/index.md
      - Multi-Process Agents: cookbook/multi-process.md
  - API Reference:
      - api/index.md
      - AgentMesh: api/agentmesh.md
      - AgentContract: api/contract.md
      - CLI: api/cli.md
  - Architecture:
      - architecture/index.md
      - Protocol: architecture/protocol.md
      - Subject Naming: architecture/subjects.md
      - Message Envelope: architecture/envelope.md
  - Decisions:
      - decisions/index.md
  - Getting Help: help.md
```

---

## Execution Strategy

Parallelize by independence:

1. **Agent A:** index.md (rewrite) + help.md (new)
2. **Agent B:** learn/ section (all 5 pages)
3. **Agent C:** concepts/errors.md + cookbook/ (index + multi-process)
4. **Agent D:** mkdocs.yml update + quickstart.md polish

Each agent reads the relevant km/ specs before writing. Each agent writes complete, publishable pages — no drafts or TODOs.

---

## Quality Gates

Before declaring v1 complete:

- [ ] Every page has code within the first scroll
- [ ] No page exceeds 200 lines (split if so)
- [ ] No "coming soon" or placeholder text
- [ ] All code examples are consistent with the API surface in CLAUDE.md
- [ ] Cross-references use relative links that resolve
- [ ] mkdocs.yml nav matches the actual file structure
- [ ] Admonitions used sparingly (max 3 per page)
