"""Object Store workspace (mesh-artifacts bucket)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nats.js.object_store import ObjectStore


class Workspace:
    """Public API for the ``mesh-artifacts`` Object Store bucket."""

    def __init__(self, store: ObjectStore):
        self._store = store

    async def put(self, key: str, data: bytes | str) -> None:
        """Store a binary artifact."""
        if isinstance(data, str):
            data = data.encode()
        await self._store.put(key, data)

    async def get(self, key: str) -> bytes:
        """Retrieve a binary artifact by key."""
        result = await self._store.get(key)
        return result.data

    async def delete(self, key: str) -> None:
        """Delete an artifact."""
        await self._store.delete(key)
