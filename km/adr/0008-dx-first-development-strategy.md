# ADR-0008: DX-first development strategy (DX -> tests -> implementation)

- **Type:** strategy
- **Date:** 2026-04-04
- **Status:** documented
- **Source:** .specstory/history/2026-04-04_09-46-15Z.md

## Context

The project needed a development methodology. The choice was between traditional inside-out (build internals first, then expose API) or outside-in (define the desired developer experience first, then build to match).

## Decision

Work backwards from the desired developer experience:

1. **DX first.** Write example code showing exactly how a library user would use the feature. This is the contract. If it looks awkward to write, fix the API before touching implementation.
2. **Tests second.** Write tests that exercise the example code. Tests must pass before implementation is considered done.
3. **Implementation last.** Write the minimum code that makes the tests pass. No speculative abstractions.

When implementing any new feature or phase, start by writing an `examples/` file showing the ideal user-facing code.

## Risks and Implications

- Requires discipline to not jump straight to implementation. Every feature starts with example code.
- May lead to API designs that are clean to use but harder to implement. This is the intended tradeoff: user experience over implementation convenience.
- Tests are always written against the public API, never internals. This makes refactoring safe.
