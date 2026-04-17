# CLI

Command-line tools for local development and mesh interaction.

## `oam mesh`

Manage the local mesh server.

### `oam mesh up`

Start a local development server with JetStream enabled and pre-created KV buckets.

```bash
oam mesh up
```

Starts on `localhost:4222` with:

- JetStream enabled
- `mesh-catalog` KV bucket
- `mesh-registry` KV bucket
- `mesh-context` KV bucket

### `oam mesh down`

Stop the local development server.

```bash
oam mesh down
```

### `oam mesh catalog`

List registered agents. Options mirror the Python `mesh.catalog()` API.

```bash
oam mesh catalog
oam mesh catalog --channel finance
```

## `oam agent`

Interact with individual agents.

### `oam agent call`

Invoke an agent and print the response.

```bash
oam agent call summarizer --data '{"text": "Hello world", "max_length": 50}'
```

### `oam agent inspect`

Show an agent's full contract (schema, description, capabilities).

```bash
oam agent inspect summarizer
```

### `oam agent health`

Check an agent's liveness status.

```bash
oam agent health summarizer
```
