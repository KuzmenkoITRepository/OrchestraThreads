"""Composition root for the agent log analysis store."""

from __future__ import annotations

from core.agent_log_analysis.store_aggregates import AggregateStoreMixin
from core.agent_log_analysis.store_base import LogStoreBase
from core.agent_log_analysis.store_correlation import CorrelationStoreMixin
from core.agent_log_analysis.store_ingest import IngestStoreMixin
from core.agent_log_analysis.store_query import QueryStoreMixin
from core.agent_log_analysis.store_raw_logs import RawLogStoreMixin


class _WriteStoreContent(
    IngestStoreMixin,
    RawLogStoreMixin,
):
    __slots__ = ()


class _ReadStoreContent(
    AggregateStoreMixin,
    CorrelationStoreMixin,
    QueryStoreMixin,
):
    __slots__ = ()


class LogStore(  # noqa: WPS215 - mixin composition requires base + 2 content groups
    LogStoreBase,
    _WriteStoreContent,
    _ReadStoreContent,
):
    """Composed store root for agent log analysis persistence."""

    __slots__ = ()
