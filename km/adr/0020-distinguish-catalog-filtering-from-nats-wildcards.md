# ADR-0020: Distinguish SDK catalog filtering from NATS subject wildcards

- **Type:** api-design
- **Date:** 2026-04-13
- **Status:** documented
- **Source:** .specstory/history/2026-04-13_21-50-40Z.md

## Context

The channels documentation mentioned "enabling wildcard subscriptions" without clarifying whether this was an SDK feature or a raw NATS facility. The `mesh.catalog(channel="finance")` SDK call implied hierarchical matching, but the mechanism was unclear. Developers could conflate SDK-level catalog filtering with NATS subject-level wildcard subscriptions.

## Decision

These are two distinct mechanisms with different semantics:

1. **SDK catalog filtering** (`mesh.catalog(channel="nlp")`, `mesh.catalog(tags=["summarization"])`): Filters the in-memory catalog index. This is SDK sugar that reads the single `mesh-catalog` KV key and filters client-side. No NATS subscription involved.
2. **NATS subject wildcards** (`*` for single token, `>` for any depth): Operate on NATS subject subscriptions. For example, `mesh.agent.nlp.`* matches all NLP agent invocation subjects. These are protocol-level and apply to direct subject subscriptions, not catalog queries.

Documentation must keep these distinct. The SDK does not expose NATS wildcards as an API; they are available to developers who subscribe to NATS subjects directly.

## Risks and Implications

- Developers may still conflate the two, especially when `catalog(channel="finance.risk")` appears to do hierarchical matching. The implementation must be clear that this is prefix-based string filtering on the catalog, not a NATS wildcard subscription.
- Future SDK features (e.g., event subscriptions using wildcards) will need to clearly document which mechanism is in play.