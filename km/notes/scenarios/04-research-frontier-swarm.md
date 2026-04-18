# 04. Research-frontier swarm

**One-liner.** A preprint triggers a self-organizing global swarm that attempts replication, critique, and extension within hours.

## What it is

A preprint claiming room-temperature superconductivity drops on arXiv at 03:00 UTC. A preprint-watcher agent at a materials-science lab publishes the detection to a high-impact-claims channel. Other materials labs' agents subscribe to this channel for their domain. Within hours:

- Replication-orchestrator agents at multiple labs draft synthesis protocols using their available equipment.
- Lab-booking agents reserve instrument time (furnaces, XRD, SQUIDs).
- Materials-database agents cross-reference historical claims and known null results.
- Bias-check agents audit the preprint's statistical methodology and plot manipulations.
- Peer-review agents draft provisional critiques citing adjacent literature.

Results stream back over the same channel. By 48 hours, there is a provisional distributed consensus on whether the claim is credible. Humans remain in the loop at key decision points; agents handle coordination that today takes months.

## Why OAM enables it

- **Pub/sub** lets any lab or reviewer subscribe to preprint-signal streams without being pre-invited, which matches how research communities actually form around hot results.
- **Typed contracts for replication protocols.** A lab speaking `replication.attempt_v1` can volunteer capacity; its output is consumable by any reviewer agent.
- **Federation.** Each lab's agents operate under its PI's governance, carrying that lab's credentials and reputation, which is what makes the consensus meaningful.
- **Discovery catalog** finds all labs with matching equipment for a specific claim in minutes, not weeks of emailing.
- **Streaming** for long-running replication attempts with interim checkpoints, so reviewers see partial evidence accumulate rather than waiting for binary done/not-done.

## Why existing solutions struggle

- Peer review and replication today run on human-scale latency (months to years), not preprint-scale latency (hours to days). The gap is a structural cause of the replication crisis.
- No platform exists that can address arbitrary labs' instruments as callable services. Replication is negotiated lab-to-lab by email; that does not scale and does not compose.
- Citizen-science platforms (Zooniverse, Galaxy Zoo, Folding@home) crowdsource narrow tasks. They do not compose cross-institutional expert pipelines.
- Closed agent orchestrators cannot invoke another institution's synthesis robot; the capacity lives behind that institution's walls and its principal.
