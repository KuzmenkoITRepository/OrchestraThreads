from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from telegram_bot_mcp.mcp.protocol import JsonDict, Payloads
from telegram_bot_mcp.request_parsing import required_text, required_user_id

if TYPE_CHECKING:
    from telegram_bot_mcp.mcp.server import TelegramBotMCPServer


ButtonMatrix = list[Any]
QuestionItems = list[JsonDict]


async def handle_tool_call(
    server: TelegramBotMCPServer,
    *,
    name: str,
    arguments: JsonDict,
) -> JsonDict:
    if name == "send_telegram_bot_message":
        return Payloads.result(
            await server.client.send_message(
                telegram_user_id=required_user_id(arguments),
                text=required_text(arguments, field_name="text"),
            )
        )
    if name == "send_telegram_bot_buttons":
        return Payloads.result(
            await server.client.send_buttons(
                telegram_user_id=required_user_id(arguments),
                text=required_text(arguments, field_name="text"),
                buttons=_required_buttons(arguments),
            )
        )
    if name == "create_telegram_bot_survey":
        return Payloads.result(
            await server.client.create_survey(
                telegram_user_id=required_user_id(arguments),
                title=required_text(arguments, field_name="title"),
                questions=_required_questions(arguments),
            )
        )
    if name == "get_telegram_bot_history":
        return Payloads.result(
            await server.client.get_history(
                telegram_user_id=required_user_id(arguments),
                limit=int(arguments.get("limit") or 200),
                session_id=str(arguments.get("session_id") or "").strip() or None,
            )
        )
    return Payloads.result({"ok": False, "error": f"Unknown tool: {name}"})


def _required_buttons(arguments: JsonDict) -> ButtonMatrix:
    buttons = arguments.get("buttons")
    if not isinstance(buttons, list) or not buttons:
        raise ValueError("buttons is required")
    return buttons


def _required_questions(arguments: JsonDict) -> QuestionItems:
    questions = arguments.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions is required")
    return cast(QuestionItems, questions)
