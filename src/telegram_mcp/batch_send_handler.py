"""MCP tool handler for send_telegram_message_batch."""

from __future__ import annotations

import asyncio
from typing import Any

from telegram_mcp.mcp_protocol import Payloads, ensure_text

JsonDict = dict[str, Any]


async def handle_batch_send(
    send_one: Any,
    arguments: JsonDict,
) -> JsonDict:
    """Send same message to multiple recipients via the canonical send path."""
    ensure_text(arguments.get("message"), field_name="message")
    recipients = _parse_recipients(arguments)
    results = await _send_all(send_one, arguments, recipients)
    return Payloads.result({"ok": True, "results": results})


async def _send_all(
    send_one: Any,
    arguments: JsonDict,
    recipients: list[str],
) -> list[JsonDict]:
    coros = [_send_to_alias(send_one, arguments, alias) for alias in recipients]
    return list(await asyncio.gather(*coros))


def _parse_recipients(arguments: JsonDict) -> list[str]:
    raw = arguments.get("recipients")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("recipients is required (non-empty list of aliases)")
    return [str(alias).strip() for alias in raw if str(alias).strip()]


async def _send_to_alias(send_one: Any, arguments: JsonDict, alias: str) -> JsonDict:
    item_args = dict(arguments)
    item_args["recipient"] = alias
    try:
        raw = await send_one(item_args)
    except Exception as exc:
        return {"recipient": alias, "ok": False, "message_id": 0, "error": str(exc)}
    return _extract_item_result(raw, alias)


def _extract_item_result(raw: JsonDict, alias: str) -> JsonDict:
    content = raw.get("structuredContent", raw)
    return {
        "recipient": alias,
        "ok": bool(content.get("ok")),
        "message_id": int(content.get("message_id") or 0),
        "error": str(content.get("error") or ""),
    }
