# Technology Stack

**Analysis Date:** 2026-05-08

## Languages

**Primary:**
- Python 3.12 (3.11-3.13 supported) - All source code in `src/openagentmesh/`

## Runtime

**Environment:**
- Python 3.12 (pinned in `.python-version`)
- Async runtime: asyncio (built-in, no external event loop library)

**Package Manager:**
- uv - Modern Python package manager
- Lockfile: `uv.lock` (committed)

## Frameworks

**Core:**
- nats-py 2.14.0+ - NATS client library for message bus communication
  - Location: `src/openagentmesh/_mesh.py`, `src/openagentmesh/_invocation.py`, `src/openagentmesh/_discovery.py`
  - Provides: JetStream (event streaming), KeyValue (distributed registry)

**CLI:**
- typer 0.24.1+ - Type-hint-driven CLI framework
  - Location: `src/openagentmesh/cli/` (entry point: `src/openagentmesh/cli/__init__.py`)
  - Commands: `oam mesh`, `oam agent`, `oam demo`

**Data Validation & Serialization:**
- pydantic 2.12.5+ - Data validation and JSON Schema generation from type hints
  - Location: Throughout (`src/openagentmesh/_models.py`, `src/openagentmesh/_handler.py`, demos)
  - Use: AgentSpec, AgentContract, CatalogEntry input/output models

**Testing:**
- pytest 9.0.2+ - Test runner
- pytest-asyncio 1.3.0+ - Async test support (asyncio_mode: auto)
  - Config: `pyproject.toml` [pytest.ini_options]
  - Location: `tests/`

**Build/Dev:**
- ruff 0.15.9+ - Linter and formatter
  - Config: `pyproject.toml` [tool.ruff]
  - Rules: E, F, I, UP, B, SIM (ignore E501 line length)
- zensical 0.0.32+ - Static site generator for documentation (Rust-based Material for MkDocs successor)
  - Config: `mkdocs.yml`
  - Location: `docs/` (source), `site/` (generated output, gitignored)
- ty 0.0.28+ - Virtual environment management
  - Config: `pyproject.toml` [tool.ty.environment]
- uv_build 0.9.27+ - Build backend for packaging

## Key Dependencies

**Critical:**
- nats-py 2.14.0+ - Why it matters: Entire mesh communication fabric depends on NATS client stability. KV and JetStream are core abstractions for registry, discovery, and message delivery.
- pydantic 2.12.5+ - Why it matters: Type inference and JSON Schema generation are central to the DX (ADR-0031). Validation happens at handler registration and request/response boundaries.
- typer 0.24.1+ - Why it matters: CLI entrypoint (`oam` command). Type hints drive `agentmesh up`, `agentmesh agent list`, etc.

**Optional (Demo only):**
- openai 1.0.0+ - Included in `demo` dependency group (not required for core SDK)
  - Location: Not directly imported in SDK; intended for demo recipes where agents call LLMs
  - Installed via: `uv pip install -e '.[demo]'`

## Configuration

**Environment:**
- `OAM_URL` - Mesh server URL. Precedence: CLI flag `--url` > env var `OAM_URL` > `.oam-url` file (walked up from cwd) > default `nats://localhost:4222`
  - Configured in: `src/openagentmesh/cli/_config.py`
- No other env vars required; secrets are not part of Phase 1 MVP

**Build:**
- `pyproject.toml` - Project metadata, dependencies, tool config
- `mkdocs.yml` - Documentation site config (Material theme, search, tags plugins)

## Platform Requirements

**Development:**
- Python 3.11, 3.12, or 3.13
- uv package manager
- NATS server (either system-installed or auto-downloaded to `~/.agentmesh/bin/`)
- curl - Used to download nats-server binary
- tar/zip - Used to extract nats-server archive
- Git (for version control)

**Production (Remote Mesh):**
- External NATS server with JetStream and KeyValue enabled
- Network connectivity to NATS at specified URL (e.g., `nats://nats.example.com:4222`)

**Testing/Demo (Embedded Mesh):**
- Same as development; uses `AgentMesh.local()` which auto-manages embedded NATS subprocess
- NATS binary downloaded on-demand to `~/.agentmesh/bin/nats-server` (v2.10.24)

## Embedded NATS

**Version:** 2.10.24 (pinned in `src/openagentmesh/_local.py`)

**Download Behavior:**
- Triggered by `AgentMesh.local()` context manager or `agentmesh up` CLI command
- Auto-downloads to `~/.agentmesh/bin/nats-server` if not found in PATH
- Downloads from: `https://github.com/nats-io/nats-server/releases/download/v2.10.24/...`
- Platform-aware: darwin/linux/windows, amd64/arm64 detection
- Cached: Subsequent runs reuse existing binary

**Subprocess Management:**
- Started as child process with ephemeral random port (or specified via CLI)
- JetStream enabled by default (event streaming)
- KeyValue enabled by default (distributed registry for catalog, agent contracts)
- Killed on `AgentMesh.local()` context exit

---

*Stack analysis: 2026-05-08*
