# The Protocol

OpenAgentMesh is protocol-first. The Python SDK is a convenience layer over a wire protocol any NATS client in any language can implement.

| Topic | Description |
|-------|-------------|
| [Wire Protocol](protocol.md) | Subjects, registry tiers, JetStream buckets, consistency model |
| [Subject Naming](subjects.md) | NATS subject hierarchy for agents, registry, health, events |
| [Message Envelope](envelope.md) | Headers and body format for requests and responses |
