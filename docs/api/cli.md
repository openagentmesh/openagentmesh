# CLI

Command-line tools for local development.

## Commands

### `mesh up`

Start a local NATS server with JetStream enabled and pre-created KV buckets.

```bash
mesh up
```

Starts NATS on `localhost:4222` with:

- JetStream enabled
- `mesh-catalog` KV bucket
- `mesh-registry` KV bucket

### `mesh status`

Show registered agents and their health status.

```bash
mesh status
```

Output includes agent name, channel, health state, and last heartbeat.
