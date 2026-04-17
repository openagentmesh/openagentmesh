# CLI

Command-line tools for local development.

## Commands

### `oam mesh up`

Start a local NATS server with JetStream enabled and pre-created KV buckets.

```bash
oam mesh up
```

Starts NATS on `localhost:4222` with:

- JetStream enabled
- `mesh-catalog` KV bucket
- `mesh-registry` KV bucket
- `mesh-context` KV bucket

### `oam mesh catalog`

List registered agents.

```bash
oam mesh catalog
```

Output includes agent name, channel, capabilities, and version.
