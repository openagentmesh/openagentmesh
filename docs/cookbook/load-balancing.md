# Automatic Load Balancing

Run multiple instances of the same agent. Requests spread across them automatically. No configuration, no service discovery, no load balancer. NATS queue groups handle it.

This recipe demonstrates the zero-config scaling story: you scale by running more copies.

## The Code

```python
--8<-- "src/openagentmesh/demos/load_balancing.py"
```

## Run It

```bash
oam demo run load_balancing
```

## How It Works

Every `@mesh.agent` subscription uses a NATS queue group named after the agent. When multiple processes register the same agent name, NATS treats them as members of the same group and distributes messages round-robin across the group.

```mermaid
sequenceDiagram
    participant Client
    participant NATS
    participant I1 as instance-1
    participant I2 as instance-2
    participant I3 as instance-3

    Client->>NATS: 10 concurrent mesh.call("translator", ...)
    NATS->>I1: Request #0
    NATS->>I2: Request #1
    NATS->>I3: Request #2
    NATS->>I1: Request #3
    Note over NATS: Round-robin across queue group members
    I1-->>NATS: TranslateOutput
    I2-->>NATS: TranslateOutput
    I3-->>NATS: TranslateOutput
    NATS-->>Client: All 10 results
```

Key properties:

- **No registration changes.** Each instance registers the same agent name and contract. The catalog shows one agent, not three.
- **No client changes.** `mesh.call("translator", ...)` is identical whether one or fifty instances are running.
- **Automatic rebalancing.** Kill an instance and its share redistributes instantly. Start a new one and it joins the group.
- **Per-message, not per-connection.** Unlike HTTP load balancers, each individual request is routed independently. No sticky sessions, no connection draining.
