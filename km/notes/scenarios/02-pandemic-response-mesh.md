# 02. Pandemic response mesh

**One-liner.** When a novel pathogen appears, a global response mesh grows within hours, composing sequencer, epi-model, protocol, and lab agents from institutions worldwide, and dissolves when the outbreak recedes.

## What it is

Day zero: an unusual case cluster is detected in a regional hospital. The hospital's sequencer agent uploads reads to a new "emergent-pathogen" channel. WHO's epi-model agent subscribes and starts estimating R0. CDC and ECDC variant-tracker agents join. Academic labs volunteer sequencing capacity via typed contracts. A protocol-synthesizer agent drafts provisional treatment guidelines as evidence accumulates. Over the following weeks the mesh grows with testing-capacity agents, vaccine-candidate agents, supply-chain agents, and public-comms agents.

Months later, as the pathogen burns out, agents depart gracefully. The mesh that existed at peak bears no resemblance to any pre-built pandemic response system because its shape was dictated by this pathogen's specific genetics, transmission, and socioeconomic context, not by a planner's guess from years prior.

## Why OAM enables it

- **Cross-org federation.** WHO, CDC, ECDC, national health services, hospitals, and academic labs participate as independent principals, each running their own agents under their own governance.
- **Typed contracts as interop layer.** "Any sequencer that speaks `sequence.upload_v1`" is a runtime claim; no central committee pre-negotiates APIs.
- **Pub/sub substrate** for event streams (novel sequences, variant detections, caseloads) at regional and global scales.
- **Discovery catalog** makes new participating institutions network-visible without registration at a central authority.
- **Death notices** detect lab outages or political withdrawal so the mesh can re-route around gaps.

## Why existing solutions struggle

- Pre-built pandemic response frameworks (WHO IHR, GISAID) are static integrations; each new data type requires a cross-institution negotiation measured in months. COVID demonstrated this failure mode in real time.
- No closed orchestrator can span national trust boundaries. Data residency, legal authority, and sovereignty forbid a single root-principal model.
- API-based integrations are bilateral; a mesh with typed contracts is multilateral by construction, which is the only shape that fits a crisis with dozens of simultaneous stakeholders.
- Existing federated scientific systems (GenBank, ClinVar) are publish-only repositories, not live agent populations. You cannot invoke a sequencer across borders, you can only download what it has already published.
