"""Error-handling pytest coverage for Telegram relay integration."""

from __future__ import annotations

from core.telegram_events import _http_send_helpers, _sse_parser


async def test_malformed_sse_event_handling() -> None:
    """Malformed SSE blocks should be ignored safely."""
    result = _sse_parser.parse_sse_block("data: invalid-json\n\n")
    assert result is None


async def test_missing_message_fields() -> None:
    """Missing message fields should fall back to safe defaults."""
    from core.telegram_events._runtime_message_handler import extract_message_data

    result = extract_message_data({"update": {"not_message": {}}}, "2024-01-01T00:00:00Z")

    assert result is not None
    assert (
        result["message_id"],
        result["sender_name"],
        result["chat_name"],
        result["text"],
    ) == (
        None,
        "Unknown",
        "Private Chat",
        "",
    )


async def test_relay_timeout_handling() -> None:
    """The timeout parsing helper should remain available."""
    assert hasattr(_http_send_helpers, "_parse_relay_response")
