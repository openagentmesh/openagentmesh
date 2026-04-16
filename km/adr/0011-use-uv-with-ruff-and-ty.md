# ADR-0011: Use uv with ruff and ty for package/dev tooling

- **Type:** tooling
- **Date:** 2026-04-04
- **Status:** accepted
- **Source:** .specstory/history/2026-04-04_14-27-58Z-i-want-to-use.md

## Context

The project needed a package manager, linter, and type checker. The choice was between traditional Python tooling (pip/poetry, flake8/pylint, mypy/pyright) and modern alternatives.

## Decision

Use uv for package and dependency management, ruff for linting/formatting, and ty for type checking. All three are Rust-based, fast, and modern. Project initialized as `uv init --lib --name agentmesh --python 3.12`.

## Risks and Implications

- uv is relatively new but rapidly maturing. Lock file format may evolve.
- ty is very early-stage (v0.0.x). May have gaps compared to mypy/pyright. Acceptable for a new project.
- All three tools are dev dependencies only; they don't affect the published package.