from __future__ import annotations

from core.orchestra_thread.store_agents import AgentStoreMixin
from core.orchestra_thread.store_base import ThreadStoreBase
from core.orchestra_thread.store_delivery import DeliveryStoreMixin
from core.orchestra_thread.store_idempotency import IdempotencyStoreMixin
from core.orchestra_thread.store_notifications import NotificationStoreMixin
from core.orchestra_thread.store_thread_creation import ThreadCreationStoreMixin
from core.orchestra_thread.store_thread_events import ThreadEventsStoreMixin
from core.orchestra_thread.store_thread_query import ThreadQueryStoreMixin


class _ThreadOperationsStoreMixin(
    ThreadQueryStoreMixin,
    ThreadCreationStoreMixin,
    ThreadEventsStoreMixin,
):
    __slots__ = ()


class _DeliveryAndNotificationStoreMixin(
    DeliveryStoreMixin,
    NotificationStoreMixin,
):
    __slots__ = ()


class _AuxiliaryStoreMixin(
    AgentStoreMixin,
    IdempotencyStoreMixin,
    _DeliveryAndNotificationStoreMixin,
):
    __slots__ = ()


class ThreadStore(
    ThreadStoreBase,
    _ThreadOperationsStoreMixin,
    _AuxiliaryStoreMixin,
):
    __slots__ = ()
