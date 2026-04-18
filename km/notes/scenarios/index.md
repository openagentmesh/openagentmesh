# Scenarios

Exploratory futures for OpenAgentMesh across domains beyond enterprise agent coordination. Each scenario assumes the full OAM vision: runtime agent spawning, autoscaling, cross-org federation, persistent addressable identity.

These are brainstorming notes, not commitments. They exist to stress-test whether OAM's specific primitives (typed contracts, two-tier discovery, pub/sub + RPC + streaming substrate, liveness semantics, federation) actually enable qualitatively new behavior, or merely optimize existing patterns.

## Selection criteria

Each scenario was chosen because runtime composition is **load-bearing**. Pre-engineering the system kills the value. Scenarios that a closed subagent orchestrator can approximate are either excluded or (in the case of #9) explicitly flagged.

## Index

| # | Scenario | One-liner | Key primitive |
|---|----------|-----------|---------------|
| [01](01-clinical-team-per-patient.md) | Clinical team-per-patient | Each ER case summons its own specialist population | Two-tier discovery + federation + death notices |
| [02](02-pandemic-response-mesh.md) | Pandemic response mesh | Outbreak-shaped global mesh grows in hours, dissolves when it recedes | Cross-org federation + typed contracts |
| [03](03-self-writing-simulations.md) | Self-writing simulations | Policy what-ifs recruit models from across institutions | Typed contracts as simulation interfaces |
| [04](04-research-frontier-swarm.md) | Research-frontier swarm | Preprint triggers global replication and critique within 48h | Pub/sub + federation + streaming |
| [05](05-app-as-agent-recruiter.md) | App-as-agent-recruiter | Thin SaaS shells summon third-party capability agents per user | Runtime catalog discovery |
| [06](06-personal-agent-ecology.md) | Personal agent ecology | Life events populate and depopulate a user's mesh | Persistent identity + federation |
| [07](07-ephemeral-commerce.md) | Ephemeral commerce | Marketplace infrastructure summoned per trade, dissolves at settlement | Multi-party membership + channel lifecycle |
| [08](08-crisis-fusion-cell.md) | Crisis fusion cell | Multi-agency disaster mesh survives shift changes, adapts to crisis type | Federation + envelope metadata + liveness |
| [09](09-self-assembling-red-team.md) | Self-assembling red team | Adversary simulation agents generated to match current threat surface | Cross-org threat intel federation |
| [10](10-cognitive-exoskeleton.md) | Cognitive exoskeleton | Agent mesh assembles around a one-shot venture for its duration | Persistent identity + replaceable contracts |

## How to read these

Each file is structured as:

1. **One-liner.** The scenario in a sentence.
2. **What it is.** Concrete walk-through of who participates, lifecycle, and what the user experiences.
3. **Why OAM enables it.** The specific OAM primitives that carry the weight.
4. **Why existing solutions struggle.** Competitors in the adjacent space (MCP registries, closed subagent orchestrators, SaaS bundles, federated science platforms, BAS tools, etc.) and what structural property each lacks.

## Relationship to ADRs and specs

Scenarios are upstream of ADRs. If a scenario surfaces a gap in the current protocol (e.g., a primitive OAM needs to carry the scenario cleanly), it becomes an input to discussion-status ADRs in `km/adr/`. Not every scenario will or should drive ADR work; the set exists mainly to sharpen positioning and to pressure-test the protocol against ambitious uses.

## Status

Brainstormed: 2026-04-17. No scenario is committed to the roadmap. Phase 1 (MVP) remains the current implementation focus; see `CLAUDE.md` for the roadmap.
