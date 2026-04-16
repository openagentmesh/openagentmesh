# OpenAgentMesh docs structure

## Outline

- Quickstart
- The why and the what of OpenAgentMesh
  - The Enterprise landscape for multi agent systems
  - OAM and MCP
  - OAM and A2A
  - Building the internet of agents (we're missing the DNS system, this can help)
  - Technology Stack (NATS, Pydantic, etc.)
- Concepts
  - Agents, tools and resources
  - Type validation
  - Discovery
  - Interaction patterns
    - Sync request-reply
    - Async request-reply 
    - Pub-Sub
  - KV and Object stores
  - Observability
  - Security (Auth/n/z)
  - MCP & A2A integration
  - Plugins (v2?)
  - Errors
- Cookbook
  - Shared context
    - Dynamic task lists for multi-agent goals
    - Creating a painting through incremental improvements
- API Documentation
- Getting Help (discord channel, GitHub, Progress Lab email for enterprise support)
- OAM in the wild (if and when it will actually be used by others)

## Quickstart outline

- Enterprise ready multi-agent frameworks. Multi-language, multi-process, self-discovering

### Your first multi-agent system in x lines

```
# Download openagentmesh, e.g. pip install

# Run local
mesh.local()

@agent1
# Not just agents
@tool

@agent2 (calls agent 1/tool)

mesh.run()

```

### Decoupling

The mesh allows agents on different processes, servers and even regions to collaborate seamlessly sharing context and artifacts.

### Discovery

```
Mesh.discover
Mesh.catalog
```

### Typing and Validation

Every tool described with rich input output schemas that are automatically enforced via pydantic

```
# example of 422 request
```

### Multi process/language

Develop agents and tools in both python AND typescript/javascript (go/rust/c# coming up)

```
example
```

### KV and Object Store

```
example of shared context/artifacts, e.g. plan, tasks, generated code/files, etc.
```

### Integrated OTel logging and tracing

```mesh.metrics)
mesh.metrics
mesg.logs
```

### Why not just direct function call?

Direct tool use and multiagent interaction requires knowledge of the toolsets and agent prompts in advance. With mesh you can register new tools and agents at anytime from anywere and have existing agents pick them up with no additional effort. 

### Why not just MCP?

MCP is fully supported:

```
mesh.add_mcp
mesh.to_mcp
```

But Sometimes MCPs are “too much”: in an enterprise scenario bloating the context with hundreds of specs makes tool selection brittle. With mesh.discover context a catalog of hundreds of agents can be easily ingested in a single context window and navigated through filtering. 

Or not enough: mesh also allows more advanced, flexible and composable patterns and provide utilities out of the box

#### Auth n/z?

TBD

#### Native pub/sub and fan out

#### Enterprise collaboration

Also, in enterprise settings where multiple teams need to collaborate, a new MCP from a team requires every user/consumer of MCP clients to set the server up manually, which implies they have been communicated of its existence before. OAM allows automatic discovery with no effort on the side of clients.

#### IoT and real time data

MCPs are meant to be consumed by MCP clients, which interact with LLMs, which are notoriously slow in processing data compared to the world of streaming data. The Mesh allows a wider range of systems to interact with each other using a shared protocol.

### Components

Mesh leverages NATS, a low latency (s) messaging system and its persistence engine JetStream, which provides Kafka style pub-sub, adding rep-reply patterns, KV and Object Stores out of the box. But mesh is first and foremost a protocol specification: in theory you could leverage any technology that can provide the same primitives separately.

```
class TL(MeshTransportLayer):
class KV(MeshKVStore):
class ObjStore(MeshObjectStore):
mesh = oam.CustomMesh(TL, KV, ObjStore)
```

### Scaling up and out

Same coding style whether you run a local mesh for development or multi region cluster with hundreds of agents.

### Contributing

Mesh is new way of handling multi-agent orchestration and choreography. Use cases can be many, and contributions are welcome, feel free to open an issue proposing a fix/feature or get in touch on Discord Server or write at [openagentmesh@progresslab.it](mailto:openagentmesh@progresslab.it) if you want to discuss about working together on it.