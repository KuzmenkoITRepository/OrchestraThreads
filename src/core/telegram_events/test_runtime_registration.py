from core.telegram_events.tests import test_runtime_registration as _impl


async def test_zero_consumers() -> None:
    await _impl.test_runtime_starts_with_zero_consumers()


async def test_register_idempotent() -> None:
    await _impl.test_register_agent_is_idempotent_for_duplicate_registration()


async def test_register_callback_binding() -> None:
    await _impl.test_register_agent_binds_callback_to_normalized_source_mcp_url()


async def test_register_remap_consumer_swap() -> None:
    await _impl.test_register_agent_remap_starts_new_consumer_and_stops_old_unused_consumer()


async def test_stop_active_consumers() -> None:
    await _impl.test_stop_stops_all_active_consumers()
