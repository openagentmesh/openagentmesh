# 01. Clinical team-per-patient

**One-liner.** Each case in the ER summons its own population of specialist agents based on presenting symptoms, confers on that patient, then dissolves.

## What it is

A patient arrives with chest pain, fever, and recent travel from SE Asia. Instead of routing through a fixed care pathway, an intake agent infers the relevant specialist domains and recruits agents from a standing catalog: tropical-infectious-disease, cardiology, travel-medicine, radiology, drug-interaction. These agents belong to their respective departments, and in federated scenarios to their respective hospitals or academic centres that publish them. They confer on this patient via a transient case channel, publish findings, and exit.

The next patient recruits a different cast. Over time, rare but important specialist agents (rickettsial-infection, Marfan screening, migrant-TB) become network-visible without ever being part of a pre-built protocol. Medicine stops being protocol-driven and becomes population-driven: the team fits the patient, not the other way around.

## Why OAM enables it

- **Two-tier discovery** (catalog then contract) lets the intake agent search "any specialist matching this symptom cluster" at LLM-native cost, roughly 20 to 30 tokens per catalog entry.
- **Typed contracts** per specialty let the intake agent dispatch with schema-validated inputs, so each specialist agent can be authored independently of the orchestrator.
- **Federation across hospitals** lets a community hospital summon a tertiary centre's tropical-medicine specialist for a single case without pooling PHI.
- **Queue groups** let a busy specialty horizontally scale across instances with no orchestrator changes.
- **Liveness and death notices** let the intake agent detect a silent specialist and escalate, which becomes a safety property in acute care.

## Why existing solutions struggle

- Pre-built care pathways (Epic, Cerner) enumerate common cases and degrade on anything unusual; the long tail is exactly where diagnostic errors concentrate.
- Closed subagent orchestrators can spawn specialists locally, but those specialists are not owned by their institutions and cannot carry institutional credentials, domain-specific training data, or malpractice accountability.
- Cross-hospital federation requires PHI to stay local; a single orchestrator spawning subagents across institutions is legally and architecturally impossible under HIPAA / GDPR / national health data laws.
- MCP-style tool registries assume the tools are reachable; they do not model a live population with death notices, so an absent specialist is a silent error rather than an alarm.
