from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


def _report_failed_dispatch(
    process_entry: Callable[[Any], Awaitable[None]],
    error_text: str,
) -> None:
    owner = getattr(process_entry, "__self__", None)
    hooks_factory = getattr(owner, "_queue_processing_hooks", None)
    if hooks_factory is None:
        return
    hooks = hooks_factory()
    hooks.on_failed_dispatch(error_text)


class _QueueProcessor:
    def __init__(self, config: Any | None = None) -> None:
        self._config = config

    async def run_queue(self) -> None:
        config = self._require_config()
        while True:
            entry = config.claim_next_entry()
            if entry is None:
                return
            await self._process_single_queue_entry(entry)

    async def run_dispatch(
        self,
        context: Any,
        event: Any,
        dispatch_id: str,
        artifact_dir: Any,
        record_result: Callable[[Any, Any, str, dict[str, Any]], None],
    ) -> None:
        try:
            result = await context.hooks.run_agent_mux(
                event=event,
                dispatch_id=dispatch_id,
                artifact_dir=artifact_dir,
            )
        except BaseException:
            await self._clear_dispatch_context(context, dispatch_id)
            raise
        try:
            record_result(context, event, dispatch_id, result)
        except BaseException:
            await self._clear_dispatch_context(context, dispatch_id)
            raise
        await self._clear_dispatch_context(context, dispatch_id)

    async def _process_single_queue_entry(self, entry: Any) -> None:
        config = self._require_config()
        attempts = int(entry.payload.get("attempt_count") or 0)
        try:
            await config.process_entry(entry)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._handle_queue_error(entry, attempts, exc)
            return
        config.complete_entry(entry)

    async def _handle_queue_error(self, entry: Any, attempts: int, exc: Exception) -> None:
        config = self._require_config()
        error_text = str(exc)
        _report_failed_dispatch(config.process_entry, error_text)
        if attempts + 1 >= config.max_attempts:
            logger.warning("discarding queue entry %s after error: %s", entry.queue_id, exc)
            config.discard_entry(entry, error_text)
            return
        logger.warning("requeueing queue entry %s after error: %s", entry.queue_id, exc)
        config.requeue_entry(entry, error_text)
        await asyncio.sleep(min(5, attempts + 1))

    async def _clear_dispatch_context(self, context: Any, dispatch_id: str) -> None:
        context.runtime_state.clear_active_dispatch(dispatch_id)
        context.hooks.clear_active_context()
        await context.hooks.clear_active_dispatch_state()

    def _require_config(self) -> Any:
        assert self._config is not None
        return self._config
