# ADR-0053: Chat integration framework and DiscordBridge

- **Type:** integration / api-design
- **Date:** 2026-04-27
- **Status:** spec
- **Depends on:** ADR-0052 (generic agent sources)
- **Source:** conversation (need to control agent personas from Discord channels; manufacturing platform downstream)

## Context

OAM's value is most visible when agents are reachable from real interaction surfaces. Chat platforms (Discord, Slack, Teams) are a natural fit: typed pub/sub semantics, channel-based segmentation, low operational overhead. They also serve as a testbed for distributed agentic patterns before applying them in enterprise contexts (manufacturing platform, internal tooling).

The immediate goal is a Discord integration that lets a team of persona agents (sales coach, project manager, SEO assistant, etc.) be invoked from Discord channels. The same pattern should generalise to Slack and Teams later without rewriting agent code.

This ADR defines:

1. A tool-agnostic chat integration framework: `ChatBridge` Protocol, `ChatInbound` / `ChatOutbound` Pydantic models, and shared lifecycle expectations.
2. `DiscordBridge` as the first concrete implementation, consuming the `Source` API from ADR-0052.

## Decision

### Layered design

```
openagentmesh.integrations.chat              # shared framework
├── ChatInbound, ChatOutbound                 # Pydantic wire models
├── ChatBridge (Protocol)                     # bridge contract
└── filters                                   # helpers: startswith, mentions, from_user

openagentmesh.integrations.chat.discord       # first impl
└── DiscordBridge                             # concrete bridge
```

`ChatBridge` is a Protocol, not an abstract base class. The Slack and Teams bridges (future) will conform to it without inheritance. The Protocol's surface is intentionally tiny: lifecycle (`__aenter__`/`__aexit__`) and a `channel(...)` method that returns a `Source` (ADR-0052).

### Wire models

```python
from pydantic import BaseModel
from typing import Any

class ChatInbound(BaseModel):
    text: str
    author_id: str          # provider-agnostic string
    author_name: str
    channel_id: str
    message_id: str
    reply_to: str | None = None
    metadata: dict[str, Any] = {}  # provider-specific extras (guild_id, thread_ts, etc.)

class ChatOutbound(BaseModel):
    text: str
    channel_id: str
    reply_to: str | None = None
```

IDs are strings across all providers. Discord IDs are integers natively but cast to string for cross-provider parity. Provider-specific fields (Discord guild_id, Slack thread_ts, Teams tenant) live under `metadata`.

### `ChatBridge` Protocol

```python
class ChatBridge(Protocol):
    async def __aenter__(self) -> "ChatBridge": ...
    async def __aexit__(self, *exc) -> None: ...
    def channel(self, channel_id: str | int, *, filter: Callable | None = None) -> Source: ...
    def inbound_subject(self, channel_id: str | int) -> str: ...
    def outbound_subject(self, channel_id: str | int) -> str: ...
```

### Subject convention

Each bridge defines its own subject root. The convention is `{root}.{channel_id}.{direction}`:

- Discord (root `chat.discord`): `chat.discord.{channel_id}.inbound` / `.outbound`.
- Slack (root `chat.slack`): may need workspace prefix; deferred to Slack bridge ADR.

Subjects are auto-derived from the channel ID. The user does not pass subject strings; they pass channel IDs and let the bridge compute subjects.

### Source semantics for chat (default reply behaviour)

A chat source binds an agent to BOTH the inbound and outbound subjects of a channel. The default reply policy is "reply to the same channel, threaded to the invoking message":

- Handler returns `str` → bridge wraps as `ChatOutbound(text=ret, channel_id=msg.channel_id, reply_to=msg.message_id)` and publishes to outbound subject.
- Handler returns `None` → no reply (lets the agent self-filter when it has nothing to say).
- Handler returns `ChatOutbound` directly → use as-is. Escape hatch for replies to a different channel, no threading, etc.

### Code sample (the DX contract)

```python
import os
from openagentmesh import AgentMesh, AgentSpec
from openagentmesh.integrations.chat import filters
from openagentmesh.integrations.chat.discord import DiscordBridge

SALES = 1234567890123456789
PM = 2345678901234567890

mesh = AgentMesh()
discord = DiscordBridge(
    mesh,
    channels=[SALES, PM],
    token=os.environ["DISCORD_BOT_TOKEN"],  # or implicit env fallback
)

# Persona agents are pure mesh agents. Domain-shaped contracts. Reusable.
@mesh.agent(
    AgentSpec(name="sales-coach", description="Sales coaching assistant"),
    sources=[discord.channel(SALES, filter=filters.startswith("/coach "))],
)
async def coach(text: str) -> str:
    # text is the raw message body; the source already filtered by prefix
    return await llm.complete(f"Sales coach: {text}")

@mesh.agent(
    AgentSpec(name="project-manager", description="Project management assistant"),
    sources=[discord.channel(PM, filter=filters.startswith("/pm "))],
)
async def pm(text: str) -> str:
    return await llm.complete(f"PM: {text}")

# Cross-platform persona: same agent, two chat sources.
# (Slack bridge is hypothetical for now.)
# @mesh.agent(
#     AgentSpec(name="sales-coach"),
#     sources=[
#         discord.channel(SALES, filter=filters.startswith("/coach ")),
#         slack.channel("C123ABC", filter=filters.mentions("sales-coach-bot")),
#     ],
# )

async def main():
    async with mesh, discord:
        await asyncio.Future()
```

### `DiscordBridge` API

```python
class DiscordBridge:
    def __init__(
        self,
        mesh: AgentMesh,
        channels: list[int],
        token: str | None = None,           # falls back to DISCORD_BOT_TOKEN env
        root: str = "chat.discord",
        respond_to_bots: bool = False,      # Layer 2 default
    ): ...

    async def __aenter__(self) -> "DiscordBridge": ...
    async def __aexit__(self, *exc) -> None: ...
    def channel(self, channel_id: int, *, filter: Callable[[ChatInbound], bool] | None = None) -> Source: ...
    def inbound_subject(self, channel_id: int) -> str: ...
    def outbound_subject(self, channel_id: int) -> str: ...
```

#### Lifecycle

- `__init__`: validates config, no I/O.
- `__aenter__`: starts the `discord.py` Client in a background task, awaits the `on_ready` event (so the bot's user_id is known), then subscribes to the outbound subject for each configured channel. Outbound subject subscriber pulls `ChatOutbound` messages and posts them to Discord via the gateway.
- Inbound: `discord.py` `on_message` handler converts `discord.Message` to `ChatInbound`, applies Layer 1 + Layer 2 filters (see below), publishes to inbound subject.
- `__aexit__`: cancels background tasks, closes the gateway connection, unsubscribes outbound subjects.

#### Loop prevention (Layers 1 and 2 in v1)

**Layer 1 — self-filter (mandatory, hardcoded):**

After `on_ready`, the bridge stores its own `bot.user.id`. Every incoming message is checked: if `msg.author.id == bot.user.id`, the message is dropped before publishing to the inbound subject. This is non-optional. The bridge's outbound posts can never trigger themselves.

**Layer 2 — bot-filter (default-on, configurable):**

By default, `respond_to_bots=False` means messages where `msg.author.bot is True` are also dropped. This prevents bot-to-bot triggering chains (other Discord bots posting messages that match agent filters). Users who explicitly want bot-to-bot interaction set `respond_to_bots=True` when constructing the bridge.

Both layers run on bridge ingress, before publishing to the inbound subject. Source-level `filter` callables run AFTER these defenses.

#### Channel scope (v1)

- Guild text channels only. DMs, threads, voice, reactions, embeds, attachments are out of scope.
- One bot per `DiscordBridge` instance. Multiple bridges with the same token would conflict on the gateway connection (Discord rejects duplicate sessions).
- Required intents: `GUILDS`, `GUILD_MESSAGES`, `MESSAGE_CONTENT`. The `MESSAGE_CONTENT` intent is privileged and must be enabled in the Discord Developer Portal.

#### What is NOT in v1

- Slash commands. Deferred to ADR-0054 (or a v2 amendment to this ADR). Slash commands are typed RPC and should map to `mesh.call()` rather than pub/sub. The 3-second ack constraint and follow-up lifecycle deserve a focused design.
- DMs, threads, reactions, voice.
- Per-persona webhook avatars. Possible later; the bot will need to filter webhook messages it owns to extend Layer 1.
- Rate limiting / circuit breakers (Layer 4 from the design conversation).
- Catalog-driven slash command auto-registration.

### Packaging

`DiscordBridge` lives in `openagentmesh.integrations.chat.discord`. The `discord.py` dependency is optional, gated behind a package extra:

```
pip install openagentmesh[discord]
```

Importing the module without the extra raises `ImportError` with an actionable message. The base `openagentmesh` package has no Discord dependency.

### Tests

- Unit tests: mock `discord.py` Client at the gateway level. Inject synthetic messages into the bridge, assert correct `ChatInbound` shape on inbound subject, assert correct Discord API calls on outbound.
- Integration tests against real Discord: out of CI. A manual smoke test recipe in the cookbook; users run it against their own private test server with their own bot token.

### Cookbook recipe

`docs/cookbook/discord-personas.md`: end-to-end persona-team example. Two personas (coach and PM) on two Discord channels. Includes bot creation steps in the Discord Developer Portal, intent configuration, and the running script.

## Consequences

- New optional dependency: `discord.py>=2.x`, gated by extra.
- New public modules: `openagentmesh.integrations.chat` and `openagentmesh.integrations.chat.discord`.
- Public types: `ChatInbound`, `ChatOutbound`, `ChatBridge` (Protocol), `DiscordBridge`, filter helpers.
- Documentation: new cookbook recipe, new concepts page on chat integrations, API reference for the new modules.
- The framework Protocol (`ChatBridge`) is published with one concrete implementation. Generalisation to Slack/Teams will validate the Protocol; if the Protocol turns out to leak Discord assumptions, refactor at that point with a second concrete data point.
- Loop prevention is the bridge's responsibility, not the SDK's. The Layer 1 self-filter is a hard invariant; Layer 2 bot-filter is a sensible default.

## Alternatives Considered

**Bridge as a regular registered agent.** Rejected. The bridge is plumbing, not behaviour. Putting it in the catalog as `discord-bridge` would expose chat-shaped I/O to LLM orchestrators, who would have no useful way to invoke it. Catalog should describe domain capabilities, not infrastructure.

**Single subject for all channels, channel_id in payload.** Rejected for v1's expected use case (5+ persona channels). Per-channel subjects let each persona agent subscribe only its own subject via NATS-native filtering. Single-subject + payload-filter forces every consumer to receive every message and filter in code; smell at scale.

**Skip Layer 2 (only filter self).** Rejected. With multiple chat-driven agents in the same channel, missing Layer 2 means another bot (e.g., a Slack-bridged agent posting via webhook later) could trigger this bot's agents inadvertently. Default-on is safer; users can opt out for bot-to-bot scenarios.

**Per-channel `DiscordBridge` instances.** Rejected. Discord enforces one gateway connection per bot token. Multiple bridge instances sharing the same token cannot each open a gateway. One bridge owns the connection and listens to all configured channels.

**Build slash commands in v1.** Rejected. Slash commands have a separate interaction lifecycle (3-second ack, defer, follow-up) and a typed argument schema that maps to `mesh.call()` rather than pub/sub. Bundling them with plain message support would inflate v1 scope. Plain text gives 80% of the value (chat with persona, persona responds). v2 adds slash commands as a focused increment.

**Stacked decorator API (`@discord.bind(channel) + @mesh.agent(spec)`).** Rejected as the canonical form. Pure sugar over ADR-0052 sources, and ADR-0052's `sources=[...]` is more general (multi-source agents, cross-platform personas). The bridge may expose a single-source convenience decorator later, but it is not the canonical path.
