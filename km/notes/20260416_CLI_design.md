# CLI Design Notes

Date: 2026-04-16

## Core Decisions

- Binary name: `oam`
- NOT based on NATS CLI; NATS is one possible implementation
- Python Typer app with custom adapters per mesh primitive
- NATS users can still use NATS CLI for low-level control

## Command Tree (Draft)

### oam mesh
- `up` / `down`: local mesh lifecycle
- `connect <remote>`: connect to remote mesh
- `catalog`: list agents (options mirror Python API)
- `listen <channel>`: subscribe to a channel
- Adapter config: specify Python adapters for non-NATS implementations

### oam agent [command] \<name\> [options]
- `call`: invoke agent, get response
- `stream`: invoke agent, stream response
- `inspect`: show contract
- `health`: check agent status
- `listen`: subscribe to agent output

### oam kv
- `ls` / `get <key>` / `put <key>` / `rm <key>`
- `bucket ls` / `bucket add <name>` / `bucket rm <name>`

### oam obj
- `inspect <key>` (get headers)
- Same subcommands as kv

## Open Questions

1. **Adapter timing.** Two options: (a) plugin system with `MeshBackend` protocol and entry-point discovery, or (b) NATS-first, non-NATS is "bring your own CLI." Leaning toward (b) until a concrete second backend exists.

2. **`oam mesh listen` vs `oam agent listen`.** Listening is scoped to a channel, not the mesh. May belong under a `oam channel` group or `oam agent listen`.

3. **Agent input passing.** How does `oam agent call` receive data? Options: `--data '{...}'`, stdin pipe, `--interactive` (schema-driven prompts). All three worth supporting.

4. **KV/obj namespace.** Are these NATS-specific (`oam nats kv`) or mesh primitives (`oam kv`)? If the mesh spec defines KV buckets as protocol-level concepts, they belong at the top level. If not, they should be scoped under `oam nats`.

5. **Agent health semantics.** Spec uses disconnect advisories, not health checks. Is `oam agent health` a ping, a catalog lookup, or something else?

6. **Config file format.** `connect <remote>` implies stored profiles. Where? `~/.agentmesh/config.toml`? Env vars? Both?

7. **Output formatting.** Human-readable tables vs JSON (`--json` flag). Needs consistency from day one. Typer + rich is the natural fit.

8. **Auth for remote connections.** Credentials for `oam mesh connect`. `--creds` flag? Config file? Deferred past Phase 1?
