# 08. Crisis fusion cell

**One-liner.** A disaster event triggers a multi-agency, multi-modality agent mesh that survives shift changes, adapts to the crisis type, and dissolves when the event ends.

## What it is

An earthquake hits a region. A disaster-detection agent on the seismic network publishes the event. Within minutes:

- UAV-fleet agents (civil and military) subscribe and deploy airborne sensors.
- Satellite-imagery-segmentation agents produce damage maps from new overpass data.
- Translation agents join because affected populations speak multiple languages.
- Ham-radio-parser agents process citizen reports.
- Hospital-load agents publish capacity.
- Supply-chain agents locate and route materiel.
- Language-model agents summarize situation reports for commanders.

Each agent belongs to its home agency (civil protection, military, NGO, private operator). The cell persists for days across shift changes; human operators hand off but agents keep running. When the incident closes, agents exit gracefully. A different crisis type recruits a different cast: wildfires bring wind-model and fuel-load agents; floods bring hydrology, levee-monitor, and wildlife-evacuation agents.

## Why OAM enables it

- **Federation across agencies** with distinct classifications, trust levels, and sovereignty. No single principal owns the cell.
- **Envelope metadata** carries trust tags and classification so cross-trust composition is explicit, not accidental.
- **Liveness as safety primitive.** A sensor agent going dark is itself a signal; is it jammed, destroyed, power-lost, or offline?
- **Persistent addressable identity** across operator shifts. The agent keeps running while humans sleep.
- **Pub/sub over NATS-grade substrate** tolerates partial connectivity, which matches field conditions (satellite + LTE + mesh radios).

## Why existing solutions struggle

- Current fusion centres rely on pre-integrated software (ATAK, Palantir, Motorola CAD) bilaterally wired at deployment time. New crisis types require new integrations negotiated in peacetime, not assembled in the hour.
- Cross-agency integrations are treaty-level and rigid. OAM's contract-level interop makes multi-agency composition tactical rather than strategic.
- Closed orchestrators cannot span agency boundaries (the operator's session is not the agency's authority), and they cannot survive operator logoff. The crisis does not pause for shift change.
- Military C2 systems federate, but are expensive, closed, and slow to evolve. OAM's decoupled model lets civilian and NGO agencies participate without joining a defense stack.
