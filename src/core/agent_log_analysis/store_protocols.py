"""Typed protocols for asyncpg-backed store interactions."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

_ConnT = TypeVar("_ConnT", bound="StoreConnectionProtocol", covariant=True)


class AcquireContextProtocol(Protocol[_ConnT]):
    """Async context manager returned by pool.acquire()."""

    async def __aenter__(self) -> _ConnT: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None: ...


class TransactionContextProtocol(Protocol):
    """Async context manager returned by connection.transaction()."""

    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None: ...


class StoreConnectionProtocol(Protocol):
    """Subset of asyncpg connection methods used by store modules."""

    async def fetchval(self, query: str, *args: Any) -> Any: ...

    async def fetchrow(self, query: str, *args: Any) -> Any: ...

    async def fetch(self, query: str, *args: Any) -> list[Any]: ...

    async def execute(self, query: str, *args: Any) -> str: ...

    async def executemany(self, command: str, args: object) -> None: ...

    async def close(self) -> None: ...

    def transaction(self) -> TransactionContextProtocol: ...


class StorePoolProtocol(Protocol):
    """Subset of asyncpg pool methods used by store modules."""

    def acquire(self) -> AcquireContextProtocol[StoreConnectionProtocol]: ...

    async def close(self) -> None: ...


class SchemaCleanupConnectionProtocol(Protocol):
    """Connection protocol used for schema-drop cleanup."""

    async def execute(self, query: str, *args: Any) -> str: ...

    async def close(self) -> None: ...
