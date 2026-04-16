# ADR-0018: Use Zensical for documentation

- **Type:** tooling
- **Date:** 2026-04-13
- **Status:** accepted
- **Source:** .specstory/history/2026-04-13_19-57-02Z.md

## Context

The project needed a documentation tool for the OpenAgentMesh SDK. Two options were considered: Zensical (the Rust-based successor to Material for MkDocs, built by the same team) and Mintlify (a hosted SaaS documentation platform).

## Decision

Use Zensical. Key reasons:

- **Python ecosystem alignment.** Material for MkDocs is the de facto standard for Python SDKs (FastAPI, Pydantic, etc.). Zensical carries that lineage forward with a Rust rewrite for speed.
- **Markdown-native.** Docs live in `docs/` alongside the code, version-controlled. No proprietary format.
- **mkdocstrings compatibility.** Auto-generates API reference from Python docstrings and type hints. Critical for an SDK project.
- **Local and open-source.** No vendor lock-in to a hosted SaaS. Everything stays in the repo.
- **Backwards compatible.** Reads existing `mkdocs.yml` configuration files natively.

## Alternatives Considered

**Mintlify.** Solid hosted docs platform popular with developer tools. Rejected because it's a hosted SaaS with its own content format, adding vendor dependency. Zensical keeps everything local and open while providing the same quality output.

## Risks and Implications

- Zensical is newer (released 2026), smaller community than established Material for MkDocs, though it inherits that ecosystem.
- If Zensical diverges from mkdocstrings or MkDocs plugin compatibility, migration friction could surface.
- Documentation structure uses `docs/` as source and `site/` as build output (gitignored).