# OAM Admin UI

Browser client for the mesh (ADR-0056). React + Vite + Tailwind; the mesh
client is `@openagentmesh/sdk` (linked from `../sdk-ts`), connecting straight
to the NATS websocket listener — there is no HTTP API in between.

## Development

The SDK link resolves against `sdk-ts/dist`, so build the SDK once first:

```bash
cd sdk-ts && pnpm install && pnpm run build
cd ../ui  && pnpm install
pnpm dev          # serves the SPA + /config.json (no `oam ui` needed in dev)
```

Point it at a running dev mesh (`oam mesh up` opens the websocket listener on
mesh port + 1, 4223 by default). Override the advertised URL with
`OAM_NATS_WS_URL=ws://host:port pnpm dev`.

```bash
pnpm run typecheck
pnpm run test     # vitest + testing-library against a fake mesh client
pnpm run build    # production assets (packaged into the wheel by CI, wave 5)
```

Compiled assets are never committed: `src/openagentmesh/_ui_assets/` is
populated by the wheel-build workflow; `oam ui` serves them at runtime.
