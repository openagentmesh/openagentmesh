"""Shared context KV store (mesh-context bucket).

ADR-0025: public KV API.
ADR-0060: ergonomic extensions (list, try_cas, create, model helpers).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, TypeVar

from pydantic import BaseModel

from ._errors import KVKeyExists

if TYPE_CHECKING:
    from nats.js.kv import KeyValue


T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

# In KVStore's method signatures, `list` resolves to the sibling `list()` method
# rather than the builtin, so return annotations use this alias.
_List = list


@dataclass
class KVEntry(Generic[T]):
    """A snapshot of a KV entry. Returned by :meth:`KVStore.list` and
    :meth:`KVStore.list_models`.

    For raw byte access, ``T`` is :class:`bytes`. For model variants, ``T``
    is the validated Pydantic model.
    """

    key: str
    value: T
    revision: int
    operation: Literal["PUT", "DELETE"] = "PUT"


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
        assert kv_entry.value is not None and kv_entry.revision is not None
        self._entry = CASEntry(self._key, kv_entry.value, kv_entry.revision, self._kv)
        return self._entry

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None or self._entry is None:
            return
        await self._entry._commit()


class TryCASEntry:
    """Mutable entry for non-raising CAS attempts (ADR-0060).

    Mirrors :class:`CASEntry` but exposes a ``committed`` boolean after the
    context exits: ``True`` if the write succeeded (or no mutation was
    attempted), ``False`` if a concurrent writer changed the value before
    this attempt completed.
    """

    def __init__(self, key: str, value: bytes, revision: int, kv: KeyValue):
        self.key = key
        self.value: str = value.decode() if isinstance(value, bytes) else value
        self._revision = revision
        self._kv = kv
        self._original = self.value
        self.committed: bool = False
        self.attempted_write: bool = False

    async def _commit(self) -> None:
        from nats.js.errors import KeyWrongLastSequenceError

        if self.value == self._original:
            self.committed = True
            self.attempted_write = False
            return

        self.attempted_write = True
        data = self.value.encode() if isinstance(self.value, str) else self.value
        try:
            self._revision = await self._kv.update(self.key, data, last=self._revision)
            self.committed = True
        except KeyWrongLastSequenceError:
            self.committed = False


class TryCASContext:
    """Non-raising CAS context manager (single attempt).

    On conflict, ``entry.committed`` is ``False`` and no exception is raised.
    Use for election semantics where losing the race is data, not error.
    """

    def __init__(self, key: str, kv: KeyValue):
        self._key = key
        self._kv = kv
        self._entry: TryCASEntry | None = None

    async def __aenter__(self) -> TryCASEntry:
        kv_entry = await self._kv.get(self._key)
        assert kv_entry.value is not None and kv_entry.revision is not None
        self._entry = TryCASEntry(self._key, kv_entry.value, kv_entry.revision, self._kv)
        return self._entry

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None or self._entry is None:
            return
        await self._entry._commit()


class CASModelEntry(Generic[M]):
    """Mutable entry holding a validated Pydantic model for CAS updates."""

    def __init__(
        self,
        key: str,
        value: M,
        revision: int,
        kv: KeyValue,
        model_cls: type[M],
    ):
        self.key = key
        self.value: M = value
        self._revision = revision
        self._kv = kv
        self._model_cls = model_cls
        self._original_json = value.model_dump_json()

    async def _commit(self) -> None:
        new_json = self.value.model_dump_json()
        if new_json == self._original_json:
            return
        self._revision = await self._kv.update(
            self.key, new_json.encode(), last=self._revision,
        )


class CASModelContext(Generic[M]):
    def __init__(self, key: str, kv: KeyValue, model_cls: type[M]):
        self._key = key
        self._kv = kv
        self._model_cls = model_cls
        self._entry: CASModelEntry[M] | None = None

    async def __aenter__(self) -> CASModelEntry[M]:
        kv_entry = await self._kv.get(self._key)
        assert kv_entry.value is not None and kv_entry.revision is not None
        value = self._model_cls.model_validate_json(kv_entry.value)
        self._entry = CASModelEntry(
            self._key, value, kv_entry.revision, self._kv, self._model_cls,
        )
        return self._entry

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None or self._entry is None:
            return
        await self._entry._commit()


class TryCASModelEntry(Generic[M]):
    """Non-raising CAS entry carrying a validated Pydantic model."""

    def __init__(
        self,
        key: str,
        value: M,
        revision: int,
        kv: KeyValue,
        model_cls: type[M],
    ):
        self.key = key
        self.value: M = value
        self._revision = revision
        self._kv = kv
        self._model_cls = model_cls
        self._original_json = value.model_dump_json()
        self.committed: bool = False
        self.attempted_write: bool = False

    async def _commit(self) -> None:
        from nats.js.errors import KeyWrongLastSequenceError

        new_json = self.value.model_dump_json()
        if new_json == self._original_json:
            self.committed = True
            self.attempted_write = False
            return

        self.attempted_write = True
        try:
            self._revision = await self._kv.update(
                self.key, new_json.encode(), last=self._revision,
            )
            self.committed = True
        except KeyWrongLastSequenceError:
            self.committed = False


class TryCASModelContext(Generic[M]):
    def __init__(self, key: str, kv: KeyValue, model_cls: type[M]):
        self._key = key
        self._kv = kv
        self._model_cls = model_cls
        self._entry: TryCASModelEntry[M] | None = None

    async def __aenter__(self) -> TryCASModelEntry[M]:
        kv_entry = await self._kv.get(self._key)
        assert kv_entry.value is not None and kv_entry.revision is not None
        value = self._model_cls.model_validate_json(kv_entry.value)
        self._entry = TryCASModelEntry(
            self._key, value, kv_entry.revision, self._kv, self._model_cls,
        )
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
        assert entry.value is not None
        return entry.value.decode()

    def cas(self, key: str) -> CASContext:
        """Compare-and-swap context manager (single attempt, raises on conflict).

        For concurrent access, use ``update()`` instead. For non-raising CAS
        (election semantics), use ``try_cas()`` (ADR-0060).
        """
        return CASContext(key, self._kv)

    def try_cas(self, key: str) -> TryCASContext:
        """Non-raising CAS context manager (ADR-0060).

        On conflict, ``entry.committed`` is ``False`` and no exception is raised.
        Use for election semantics where losing the race is data, not error.

        Usage::

            async with mesh.kv.try_cas("election.key") as entry:
                if some_condition:
                    entry.value = "claimed"

            if entry.committed:
                # I won the race
                ...
        """
        return TryCASContext(key, self._kv)

    async def create(self, key: str, value: BaseModel | bytes | str) -> int:
        """Put-if-absent (ADR-0060).

        Returns the new revision number on success. Raises :class:`KVKeyExists`
        if the key already exists.
        """
        from nats.js.errors import KeyWrongLastSequenceError

        if isinstance(value, BaseModel):
            data = value.model_dump_json().encode()
        elif isinstance(value, str):
            data = value.encode()
        else:
            data = value

        try:
            return await self._kv.create(key, data)
        except KeyWrongLastSequenceError as e:
            raise KVKeyExists(key=key) from e

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
            assert kv_entry.value is not None
            current = kv_entry.value.decode()

            result = fn(current)
            new_value = result if isinstance(result, str) else await result

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

    async def list(self, prefix: str) -> _List[KVEntry[bytes]]:
        """One-shot snapshot of all entries under a prefix or wildcard (ADR-0060).

        NATS subject wildcards (``*``, ``>``) are accepted. Returns current
        entries; does not continue watching after the initial replay.
        """
        watcher = await self._kv.watch(prefix)
        entries: list[KVEntry[bytes]] = []
        try:
            async for entry in watcher:
                if entry is None:
                    # nats-py yields None when initial replay completes.
                    break
                if entry.value is None:
                    continue
                op = (
                    "DELETE"
                    if str(getattr(entry, "operation", "PUT")).upper().endswith("DELETE")
                    else "PUT"
                )
                entries.append(
                    KVEntry(
                        key=entry.key,
                        value=entry.value,
                        revision=entry.revision,
                        operation=op,
                    )
                )
        finally:
            await watcher.stop()
        return entries

    # --- Pydantic model helpers ---

    async def put_model(self, key: str, model: BaseModel) -> int:
        """Serialize ``model`` to JSON and store. Returns the revision number."""
        return await self._kv.put(key, model.model_dump_json().encode())

    async def get_model(self, key: str, model_cls: type[M]) -> M:
        """Read ``key`` and validate the JSON payload against ``model_cls``."""
        entry = await self._kv.get(key)
        assert entry.value is not None
        return model_cls.model_validate_json(entry.value)

    def cas_model(self, key: str, model_cls: type[M]) -> CASModelContext[M]:
        """Pydantic-aware CAS context manager (raises on conflict)."""
        return CASModelContext(key, self._kv, model_cls)

    def try_cas_model(self, key: str, model_cls: type[M]) -> TryCASModelContext[M]:
        """Pydantic-aware non-raising CAS context manager."""
        return TryCASModelContext(key, self._kv, model_cls)

    async def list_models(
        self, prefix: str, model_cls: type[M],
    ) -> _List[KVEntry[M]]:
        """One-shot snapshot under a prefix; each value validated to ``model_cls``."""
        raw = await self.list(prefix)
        return [
            KVEntry(
                key=e.key,
                value=model_cls.model_validate_json(e.value),
                revision=e.revision,
                operation=e.operation,
            )
            for e in raw
        ]
