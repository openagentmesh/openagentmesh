# 03. Self-writing simulations

**One-liner.** A policy or scientific what-if question recruits the specific model agents it needs from across institutions, runs the simulation, and dissolves.

## What it is

An analyst types: "what happens to EU logistics capacity if 10% of trucks are autonomous by 2030?" An orchestrator agent decomposes the question into sub-domains: traffic flow, labor markets, regulatory constraints, energy demand, weather. For each sub-domain it queries the catalog and recruits the best-matching agent: ETH Zurich's traffic model, a labor-economics agent from Bruegel, DG MOVE's regulatory model, the national weather service's climate agent.

These agents coordinate over a transient simulation channel, exchange boundary conditions via typed contracts, iterate to convergence, and produce a joint report. The next question recruits an entirely different cast. The simulation is *composed* per question, not a monolithic model with everything pre-integrated. Two orders of magnitude more policy questions become tractable because the integration cost per question drops from months to minutes.

## Why OAM enables it

- **Typed contracts as simulation interfaces.** `traffic.demand_curve_v2`, `weather.scenario_ensemble_v1`, `economy.labor_elasticity_v1`. Any agent speaking the contract can plug in.
- **Federation** lets each institution's model agent stay in that institution's environment (compute, data, governance) while participating in the joint simulation.
- **Catalog plus contract discovery** lets the orchestrator select from all models speaking a given interface, not just a pre-integrated set.
- **Streaming** lets long-running model runs emit progress so downstream consumers can react to partial results and short-circuit obviously wrong configurations.
- **Discovery costs scale with catalog size, not integration effort.** A new model joins and becomes composable immediately.

## Why existing solutions struggle

- Integrated assessment models (IAMs) in climate, economics, and energy take years to wire together. The wiring, not the science, is the bottleneck. OAM makes wiring a runtime property of the question.
- Single-orchestrator solutions (Python scripts, Jupyter notebooks, single-process agents) cannot cross institutional boundaries. The model you need is usually on someone else's cluster with its own data, and you cannot just import it.
- Federated science platforms exist (ESGF for climate, CMIP archives) but are data-only. You download outputs. You do not invoke the model.
- Closed subagent orchestrators can spawn simulation subagents in-process but lose access to any model that is not locally runnable, which is most of them for serious policy analysis.
