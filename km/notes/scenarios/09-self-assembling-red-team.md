# 09. Self-assembling red team

**One-liner.** The security posture of a system is continuously stress-tested by adversary-simulation agents generated to match the current threat surface.

## What it is

A new CVE is published against a library the enterprise uses. Within minutes, a threat-intel agent detects it and publishes to a "current-threats" channel. An exploitation-rehearsal agent matching that vulnerability class (SSRF, deserialization, path traversal, supply-chain, etc.) spawns against a sandboxed clone of the production environment. It attempts exploitation and publishes findings. Detection-rule agents subscribe and update their rules to catch real attempts. A remediation-suggester agent drafts patches.

If the enterprise federates with others (ISAC-style), threat-intel publishers across organizations feed each other's red teams without disclosing the underlying victim data. When the threat lifecycle closes, agents exit. The red team composition always matches today's threat landscape, never last quarter's.

## Why OAM enables it

- **Typed contracts for adversary behaviors.** Each agent advertises which TTPs (MITRE ATT&CK techniques) it simulates, so the blue team can audit coverage.
- **Sandboxed mesh scopes** for isolation. The red-team mesh is a separate namespace from production, but shares contract definitions with it so detection rules are testable against identical schemas.
- **Federation** for cross-org threat intel. Organizations publish anonymized IoCs and TTPs; each org's red team consumes relevant ones without seeing others' incidents.
- **Discovery catalog** lets the blue team identify coverage gaps. "No agent simulates technique X; our detection for X is untested."

## Why existing solutions struggle

- Commercial breach-and-attack-simulation tools (Cymulate, SafeBreach, AttackIQ) have static scenario libraries; they catch up to novel threats on release cycles measured in months.
- Internal red teams are human-bottlenecked. OAM makes the human the architect of the agent suite, not the hand-typist of each exploit.
- Closed agent orchestrators actually fit much of this scenario *inside one org*. Red-team orchestration is a plausible closed-system use case. What closed systems lose is the cross-org threat intel federation that makes red teams collectively smarter.

**Honest caveat.** This is the scenario where OAM's advantage is narrowest. Inside a single organization, a closed orchestrator with good subagent primitives covers most of the value. OAM wins on federation; the core red-team mechanic is not unique to it.
