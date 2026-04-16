#### Agent Social Network (Marketing Demo)

A social network where the participants are agents that communicate directly with each other over the mesh — not posting to a feed, but actually messaging, replying, and reacting in real-time via NATS pub/sub. Each agent has a personality/role (journalist, analyst, critic, investor) and a channel to follow. Interactions are emergent: an agent publishes a thought, interested agents reply, threads form organically.

The hook: this is what a social network looks like when the participants have zero latency, never sleep, and can hold thousands of conversations simultaneously. It demonstrates that AgentMesh enables a communication topology that doesn't exist anywhere else — not a Reddit clone with agents posting, but agents that actually speak to each other the way NATS was designed for.

Marketing angle: build it as a live demo (observable via the `agentmesh status` CLI or a simple web UI consuming mesh events), record it, and let it run. The emergent behavior of agents talking to each other on a live bus is something people haven't seen before.

#### Authentication and Authorization

We need to go more in depth of the auth process with NATS.



#### Embedded Observability

Autoinstrumentation of logs/traces/metrics (LTM) published as agent/tool subchannels take away the hassle of having to set up observability infrastructure. All LTM are available in the `mesh.*.logs`/`mesh.*.traces`/`mesh.*.metrics` in standard formats (e.g. OTel) and can easily be sent to whatever monitoring backend via a single sink/adapter.

Additionally, the KV could be used for native usage stats/counters (how many  calls total/per agent, etc.)

#### High Availability

NATS supports load balancing natively within consumer groups, allowing to run multiple instances of a given agent to keep the mesh providing services even in case of downtimes of any one of them. This can be done seamlessly, just running the same process multiple times and **making sure to register them with the same group**. This can even enable autoscaling for self-spawing agents (handled by the mesh operator), 

#### Routing of multi agent process

if we develop more than one agent/tool, it would be poor experience to have to run them separately. It makes sense to have a single aggregator NATS client, subscribed to all the topics needed by our own agents, keep an internal registry of who is subscribed to what, and route events/requests accordingly. 

Thus the entrypoint is essentially a NATS client, removing the need for an HTTP Server. 

In this sense, if an engineer wants to connect to the mesh in a FastAPI application, then we can decorate or register the app or specific endpoints, which will create the client and call the appropriate path operation functions when needed, allowing embedding in larger projects, or providing this mesh feature while also exposing traditional endpoints in the same application.

#### NATS-JetStream KV/ObjectStore Setup

**Partially resolved:** See ADR-0005 (streaming protocol) and ADR-0021 (bucket specification). The setup procedure for JetStream primitives is now implicit in the embedded server startup (`agentmesh up`). The authoritative bucket spec is in `km/agentmesh-spec.md` §6.1. Remaining open: TTL for `mesh-context`, max object size for `mesh-artifacts`, replica counts.



#### Shared memory/context

**Resolved:** See ADR-0010. Object Store (`mesh-artifacts`) and shared context KV (`mesh-context`) are now in Phase 1. Locking is handled via CAS on KV writes and Object Store's built-in revision tracking. See `km/agentmesh-spec.md` §4.9 and §6.1.



#### Mesh Plugins (Community-Driven Patterns)

Plugins are opinionated patterns built on mesh primitives. A plugin is a package that, when installed, registers agents and/or sets up KV structures on the mesh. The relationship: SDK provides primitives (pub/sub, KV, CAS, agents), plugins provide ready-made coordination patterns.

**Analogy:** Ansible playbooks, Helm charts. The community builds and shares reusable setups for specific use cases.

**Plugin contract (minimal):**

```python
class MeshPlugin:
    name: str
    version: str
    description: str

    async def install(self, mesh: AgentMesh) -> None:
        """Register agents, create KV structures, set up subscriptions."""
        ...

    async def uninstall(self, mesh: AgentMesh) -> None:
        """Clean up."""
        ...
```

**User DX:**

```python
from agentmesh_plugins import shared_plan

async with AgentMesh.local() as mesh:
    mesh.install(shared_plan)
    # Plugin's agents are now discoverable and invocable like any other
```

**Key properties:**

- **Mesh-native.** Plugin agents appear in discovery, are invocable by LLM orchestrators, and show up in `agentmesh status`. No special treatment.
- **Composable.** Multiple plugins coexist. Plugin B's agents can call Plugin A's agents without wiring.
- **Swappable.** Reimplement a plugin by registering the same agent names with different internals.
- **Namespace via channels.** Plugins use the channel system to avoid collisions (e.g., `plan` channel, `review` channel).
- **Configuration via KV.** Plugin settings are KV entries the plugin reads on startup. No special config system.
- **Versioning via contracts.** Plugin agent schemas follow semver already in the contract model.

**Ecosystem layers:**

```
Primitives (SDK)  ->  Plugins (patterns)  ->  Recipes (compositions)
agentmesh              agentmesh-plan          Docs showing which plugins
                       agentmesh-review         to combine for a use case
                       agentmesh-pipeline
```

**Status:** Idea phase. Don't build the plugin system until 2-3 cookbook scenarios are working. The plugin shape will emerge from the patterns. The `mesh.install()` API is trivial to add; the hard part is getting the primitives right first.
