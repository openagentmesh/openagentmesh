# ADR-0045: Unlink Cookbook Docs from Demo Modules

**Status:** implemented  
**Supersedes:** ADR-0041 (CLI demos as canonical code samples)

## Context

ADR-0041 established that CLI demo modules (`src/openagentmesh/demos/`) are the single canonical source of truth for cookbook documentation, tests, and the `oam demo` CLI. Docs embedded demo source via file-include directives; tests imported from demo modules.

In practice, demos have evolved into interactive showcases: lifecycle logging, signal handling for Ctrl+C, `.oam-url` file management, and cross-terminal interaction hints. These features make demos better as experiences but worse as teaching material. A demo optimized for "wow, there's a real system here" is not the same artifact as a minimal code sample optimized for "I can copy-paste this and understand it."

Forcing both purposes into one file creates a dual constraint that limits both.

## Decision

Unlink the cookbook documentation from demo modules:

- **Demos** (`src/openagentmesh/demos/`): Interactive CLI showcases, free to add logging, signals, lifecycle output, UX polish. Exposed via `oam demo run/list/show`.
- **Cookbook docs** (`docs/cookbook/`): Standalone inline code samples optimized for teaching one concept clearly. No file-include dependency on demo source.
- **Cookbook tests** (`tests/cookbook/`): Validate that the patterns shown in docs actually work against `AgentMesh.local()`.

The three concerns (showcase, teach, verify) are now independent and can evolve at their own pace.

## Consequences

**Positive:**
- Demos can add interactivity without breaking docs or tests
- Cookbook samples stay minimal and copy-pasteable
- No build-time coupling between docs and source tree
- Tests verify the teaching material directly, not a showcase wrapper

**Negative:**
- Two representations of similar logic (demo + doc sample) may drift
- No automatic guarantee that doc samples compile

**Mitigation:**
- Cookbook tests exercise the same patterns shown in docs, catching drift
- Docs and demos serve different audiences (learning vs. exploring), so drift is acceptable
