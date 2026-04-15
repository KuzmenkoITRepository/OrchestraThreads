from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from core.telegram_events.agent_registry import RegistrationStatus
from core.telegram_events.service.runtime import TelegramEventsService
from core.telegram_events.service.runtime_models import ManagedConsumer
from core.telegram_events.sse_event import SSEEvent


def _service() -> TelegramEventsService:
    return TelegramEventsService(
        bearer_token="test-token",
        http_host="127.0.0.1",
        http_port=0,
    )


def _managed_consumer(agent_slug: str, telegram_mcp_url: str) -> ManagedConsumer:
    return ManagedConsumer(
        agent_slug=agent_slug,
        telegram_mcp_url=telegram_mcp_url,
        events_url=f"{telegram_mcp_url.removesuffix('/mcp')}/events/telegram",
        consumer=AsyncMock(),
    )


async def test_runtime_starts_with_zero_consumers() -> None:
    service = _service()

    assert service._consumers_by_mcp_url == {}


async def test_start_skips_threads_self_registration() -> None:
    service = _service()
    shutdown_future = __import__("asyncio").get_running_loop().create_future()
    threads_client = AsyncMock()

    with (
        patch(
            "core.telegram_events.service.runtime_support.start_runtime_resources",
            new=AsyncMock(
                return_value=Mock(
                    shutdown_future=shutdown_future,
                    http_client=AsyncMock(),
                    threads_client=threads_client,
                    http_runner=Mock(),
                )
            ),
        ) as start_resources_mock,
        patch(
            "core.telegram_events.service.runtime.wait_for_shutdown",
            new=AsyncMock(),
        ) as wait_for_shutdown_mock,
    ):
        await service.start()

    start_resources_mock.assert_awaited_once()
    wait_for_shutdown_mock.assert_awaited_once_with(shutdown_future)
    threads_client.register_agent.assert_not_awaited()
    threads_client.send_heartbeat.assert_not_awaited()


async def test_register_agent_is_idempotent_for_duplicate_registration() -> None:
    service = _service()
    created_consumer = _managed_consumer("alpha", "http://relay.test/mcp")

    with patch(
        "core.telegram_events.service.runtime_registry_support.start_sse_consumer",
        new=AsyncMock(return_value=created_consumer),
    ) as start_consumer_mock:
        first = await service.register_agent(object(), "alpha", "http://relay.test/mcp/")
        second = await service.register_agent(object(), "alpha", "http://relay.test/mcp")

    assert first.status is RegistrationStatus.REGISTERED
    assert second.status is RegistrationStatus.DUPLICATE
    start_consumer_mock.assert_awaited_once()
    assert service._consumers_by_mcp_url == {"http://relay.test/mcp": created_consumer}


async def test_register_agent_binds_callback_to_normalized_source_mcp_url() -> None:
    service = _service()
    event = SSEEvent(
        event_id="evt-1",
        event_type="message",
        occurred_at="2024-01-01T00:00:00Z",
        mode="private",
        account="test",
        update={},
    )

    with (
        patch(
            "core.telegram_events.service.runtime_registry_support.start_sse_consumer",
            new=AsyncMock(),
        ) as start_consumer_mock,
        patch.object(
            service,
            "_handle_sse_event",
            new=AsyncMock(),
        ) as handle_event_mock,
    ):
        await service.register_agent(object(), "alpha", "http://relay.test/mcp/")

    await_args = start_consumer_mock.await_args
    assert await_args is not None
    consumer_config = await_args.kwargs["config"]
    await consumer_config.on_event(event)

    handle_event_mock.assert_awaited_once_with(
        event,
        source_telegram_mcp_url="http://relay.test/mcp",
    )


async def test_register_agent_remap_starts_new_consumer_and_stops_old_unused_consumer() -> None:
    service = _service()
    old_consumer = _managed_consumer("alpha", "http://relay-one.test/mcp")
    new_consumer = _managed_consumer("alpha", "http://relay-two.test/mcp")

    with (
        patch(
            "core.telegram_events.service.runtime_registry_support.start_sse_consumer",
            new=AsyncMock(side_effect=[old_consumer, new_consumer]),
        ) as start_consumer_mock,
        patch(
            "core.telegram_events.service.runtime_registry_support.stop_consumers",
            new=AsyncMock(),
        ) as stop_consumers_mock,
    ):
        first = await service.register_agent(object(), "alpha", "http://relay-one.test/mcp")
        second = await service.register_agent(object(), "alpha", "http://relay-two.test/mcp")

    assert first.status is RegistrationStatus.REGISTERED
    assert second.status is RegistrationStatus.REMAPPED
    assert second.previous_telegram_mcp_url == "http://relay-one.test/mcp"
    assert list(service._consumers_by_mcp_url) == ["http://relay-two.test/mcp"]
    assert service._consumers_by_mcp_url["http://relay-two.test/mcp"] is new_consumer
    assert start_consumer_mock.await_count == 2
    stop_consumers_mock.assert_awaited_once_with((old_consumer,))


async def test_register_agent_failure_keeps_registry_and_consumers_unchanged() -> None:
    service = _service()
    old_consumer = _managed_consumer("alpha", "http://relay-one.test/mcp")
    first = service._agent_registry.register("alpha", "http://relay-one.test/mcp")
    service._consumers_by_mcp_url[first.telegram_mcp_url] = old_consumer

    with patch(
        "core.telegram_events.service.runtime_registry_support.start_sse_consumer",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ) as start_consumer_mock:
        try:
            await service.register_agent(object(), "alpha", "http://relay-two.test/mcp")
        except RuntimeError as exc:
            assert str(exc) == "boom"
        else:
            raise AssertionError("register_agent should propagate consumer startup failure")

    start_consumer_mock.assert_awaited_once()
    registration = service._agent_registry.get_registration_for_slug("alpha")
    assert registration is not None
    assert registration.telegram_mcp_url == "http://relay-one.test/mcp"
    assert service._consumers_by_mcp_url == {"http://relay-one.test/mcp": old_consumer}


async def test_unknown_source_event_warns_and_drops_without_delivery() -> None:
    service = _service()
    service._http_client = AsyncMock()
    event = SSEEvent(
        event_id="evt-2",
        event_type="message",
        occurred_at="2024-01-01T00:00:00Z",
        mode="private",
        account="test",
        update={
            "message": {
                "id": 42,
                "from": {"id": 7, "first_name": "Bob"},
                "chat": {"id": 321, "title": "Chat"},
                "text": "Hello",
                "date": 1704067200,
            }
        },
    )

    with (
        patch(
            "core.telegram_events.service.runtime_registry_support.logger.warning",
            new=Mock(),
        ) as warning_mock,
        patch(
            "core.telegram_events.service.runtime.service_delivery.forward_delivery",
            new=AsyncMock(),
        ) as delivery_mock,
        patch.object(
            service,
            "_forward_message_event",
            new=AsyncMock(),
        ) as forward_message_mock,
    ):
        await service._handle_sse_event(event, source_telegram_mcp_url="http://unknown.test/mcp")

    warning_mock.assert_called_once_with(
        "Dropping SSE event from unknown source MCP URL: %s",
        "http://unknown.test/mcp",
    )
    delivery_mock.assert_not_awaited()
    forward_message_mock.assert_not_awaited()


async def test_stop_stops_all_active_consumers() -> None:
    service = _service()
    first_consumer = _managed_consumer("alpha", "http://relay-one.test/mcp")
    second_consumer = _managed_consumer("beta", "http://relay-two.test/mcp")
    service._consumers_by_mcp_url = {
        first_consumer.telegram_mcp_url: first_consumer,
        second_consumer.telegram_mcp_url: second_consumer,
    }

    with (
        patch(
            "core.telegram_events.service.runtime_support.stop_runtime",
            new=AsyncMock(),
        ) as stop_runtime_mock,
        patch(
            "core.telegram_events.service.runtime_support.stop_consumers",
            new=AsyncMock(),
        ) as stop_consumers_mock,
        patch(
            "core.telegram_events.service.runtime_support.close_runtime_clients",
            new=AsyncMock(),
        ) as close_clients_mock,
    ):
        await service.stop()

    stop_runtime_mock.assert_awaited_once_with(None, None)
    stop_consumers_mock.assert_awaited_once_with((first_consumer, second_consumer))
    close_clients_mock.assert_awaited_once_with(None, None)
    assert service._consumers_by_mcp_url == {}
