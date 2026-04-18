"""Shared context KV store (mesh-context bucket)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from nats.js.kv import KeyValue


class CASEntry:
    """Mutable entry for compare-and-swap updates.

    Used as: ``async with context.cas(key) as entry:``
    Modify ``entry.value`` inside the block; on exit the store
    writes the new value with a single CAS attempt.
    """

    def __init__(self, key: str, value: bytes, revision: int, kv: KeyValue):
        self.key = key
        self.value: str = value.decode() if isinstance(value, bytes) else value
        self._revision = revision
        self._kv = kv
        self._original = self.value

    async def _commit(self) -> None:
        if self.value == self._original:
            return
        data = self.value.encode() if isinstance(self.value, str) else self.value
        self._revision = await self._kv.update(self.key, data, last=self._revision)


class CASContext:
    """Async context manager for a single CAS read-modify-write attempt.

    For concurrent access to the same key, use ``context.update(key, fn)``
    which retries the mutation function on conflict.
    """

    def __init__(self, key: str, kv: KeyValue):
        self._key = key
        self._kv = kv
        self._entry: CASEntry | None = None

    async def __aenter__(self) -> CASEntry:
        kv_entry = await self._kv.get(self._key)
        self._entry = CASEntry(self._key, kv_entry.value, kv_entry.revision, self._kv)
        return self._entry

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None or self._entry is None:
            return
        await self._entry._commit()


class KVStore:
    """Public API for the ``mesh-context`` KV bucket."""

    def __init__(self, kv: KeyValue):
        self._kv = kv

    async def put(self, key: str, value: str | bytes) -> int:
        """Store a value. Returns the revision number."""
        data = value.encode() if isinstance(value, str) else value
        return await self._kv.put(key, data)

    async def get(self, key: str) -> str:
        """Retrieve a value by key."""
        entry = await self._kv.get(key)
        return entry.value.decode()

    def cas(self, key: str) -> CASContext:
        """Compare-and-swap context manager (single attempt).

        Use for simple cases where conflicts are unlikely.
        For concurrent access, use ``update()`` instead.

        Usage::

            async with context.cas("my-key") as entry:
                data = json.loads(entry.value)
                data["count"] += 1
                entry.value = json.dumps(data)
        """
        return CASContext(key, self._kv)

    async def update(
        self,
        key: str,
        fn: Callable[[str], str | Awaitable[str]],
        max_retries: int = 10,
    ) -> None:
        """CAS update with automatic retry on conflict.

        ``fn`` receives the current value and returns the new value.
        On revision conflict, the value is re-read and ``fn`` is called
        again with the fresh value. Safe for concurrent access.

        Usage::

            async def increment(value: str) -> str:
                count = int(value) + 1
                return str(count)

            await context.update("counter", increment)
        """
        from nats.js.errors import KeyWrongLastSequenceError

        for _ in range(max_retries):
            kv_entry = await self._kv.get(key)
            current = kv_entry.value.decode()

            result = fn(current)
            if isinstance(result, Awaitable):
                new_value = await result
            else:
                new_value = result

            if new_value == current:
                return

            try:
                await self._kv.update(key, new_value.encode(), last=kv_entry.revision)
                return
            except KeyWrongLastSequenceError:
                continue

        raise RuntimeError(f"CAS update failed after {max_retries} retries for key '{key}'")

    async def watch(self, key: str) -> AsyncIterator[str]:
        """Watch a key for changes. Yields the new value on each update."""
        watcher = await self._kv.watch(key)
        async for entry in watcher:
            if entry is None or entry.value is None:
                continue
            yield entry.value.decode()

    async def delete(self, key: str) -> None:
        """Delete a key."""
        await self._kv.delete(key)
