"""Discovery primitives: catalog, contract, discover."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ._models import AgentContract, CatalogEntry, MeshError
from ._subjects import compute_registry_key

if TYPE_CHECKING:
    from ._mesh import AgentMesh


class DiscoveryMixin:

    async def catalog(
        self: AgentMesh,
        channel: str | None = None,
        tags: list[str] | None = None,
        streaming: bool | None = None,
        invocable: bool | None = None,
    ) -> list[CatalogEntry]:
        """Lightweight agent listing from the catalog cache (ADR-0028, ADR-0032).

        ``channel`` filters by name prefix: an entry matches when its name
        equals ``channel`` or starts with ``channel + "."`` (ADR-0049).
        """
        await self._subscribe_pending()

        entries = list(self._catalog_cache.values())

        if channel is not None:
            prefix = f"{channel}."
            entries = [
                e for e in entries
                if e.name == channel or e.name.startswith(prefix)
            ]
        if tags is not None:
            tag_set = set(tags)
            entries = [e for e in entries if tag_set.issubset(set(e.tags))]
        if streaming is not None:
            entries = [e for e in entries if e.streaming == streaming]
        if invocable is not None:
            entries = [e for e in entries if e.invocable == invocable]

        return entries

    async def contract(self: AgentMesh, name: str) -> AgentContract:
        """Fetch full contract from the registry (authoritative)."""
        assert self._registry_kv is not None

        if name in self._agents:
            _, _, c = self._agents[name]
            return c

        try:
            entry = await self._registry_kv.get(compute_registry_key(name))
        except Exception:
            raise MeshError(code="not_found", message=f"Agent '{name}' not found")

        data = json.loads(entry.value)
        xam = data.get("x-agentmesh", {})
        caps = data.get("capabilities", {})

        return AgentContract(
            name=data["name"],
            description=data["description"],
            version=data.get("version", "0.1.0"),
            capabilities=caps,
            skills=data.get("skills", []),
            subject=xam.get("subject", ""),
            tags=xam.get("tags", []),
            invocable=caps.get("invocable", True),
            streaming=caps.get("streaming", False),
            chunk_schema=xam.get("chunk_schema"),
        )

    async def discover(self: AgentMesh, channel: str | None = None) -> list[AgentContract]:
        """Full contract listing. Heavier than catalog(), authoritative."""
        catalog_entries = await self.catalog(channel=channel)
        contracts = []
        for entry in catalog_entries:
            try:
                contracts.append(await self.contract(entry.name))
            except MeshError:
                continue
        return contracts
