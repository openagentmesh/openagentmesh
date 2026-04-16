# ADR-0017: Rebrand to OpenAgentMesh (OAM)

- **Type:** strategy
- **Date:** 2026-04-13
- **Status:** discussion
- **Source:** km/notes/Docs structure.md, direct user confirmation

## Context

Project repo named `openagentmesh` from inception. Docs drafts use "OpenAgentMesh" and abbreviation "OAM" consistently. Spec files and code still use "AgentMesh". Name needs alignment across all artifacts.

## Decision

- **Project name:** OpenAgentMesh (OAM)
- **Python package:** `openagentmesh` (PyPI name)
- **Code class name:** `AgentMesh`. Stays as-is. Short, clean API. `from openagentmesh import AgentMesh`.
- **CLI command:** `agentmesh` or `oam` (TBD)
- **Docs/marketing:** "OpenAgentMesh" or "OAM"

The split is intentional: package/brand is "OpenAgentMesh", but the developer-facing class stays `AgentMesh` for ergonomics. Same pattern as FastAPI (package `fastapi`, class `FastAPI`).

## Risks and Implications

- All km/ spec files reference "AgentMesh"; need systematic rename to "OpenAgentMesh" where referring to the project (not the class).
- CLAUDE.md, README, docs all need alignment.
- PyPI name `openagentmesh` should be reserved early.