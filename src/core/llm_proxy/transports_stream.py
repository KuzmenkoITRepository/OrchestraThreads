from __future__ import annotations

import json
import uuid
from typing import Any

import requests

from core.llm_proxy.codex_oauth import (
    is_account_unavailable_message,
    is_retryable_codex_error_message,
)
from core.llm_proxy.protocol import AssistantTextItem, CodexUpstreamError, ToolCallItem


def consume_codex_stream(
    *,
    response: requests.Response,
    profile_id: str,
    cancel_event: Any,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "response_items": [],
        "current_text": None,
        "current_tool": None,
        "usage": None,
        "stop_reason": "stop",
    }
    for raw_line in response.iter_lines(decode_unicode=True):
        if cancel_event is not None and cancel_event.is_set():
            response.close()
            raise CodexUpstreamError(
                "Codex request cancelled",
                profile_id=profile_id,
                retriable=True,
            )
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", "replace")
        if not raw_line or not raw_line.startswith("data:"):
            continue
        payload = raw_line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if _handle_event(event=event, profile_id=profile_id, state=state):
            break
    return state


def _handle_event(*, event: dict[str, Any], profile_id: str, state: dict[str, Any]) -> bool:
    event_type = str(event.get("type") or "")
    if event_type == "error":
        message = str(event.get("message") or event.get("code") or event)
        raise CodexUpstreamError(
            f"Codex error: {message}",
            profile_id=profile_id,
            retriable=is_retryable_codex_error_message(message),
            account_unavailable=is_account_unavailable_message(message),
        )
    if event_type == "response.failed":
        raise _response_failed_error(event=event, profile_id=profile_id)
    if event_type == "response.output_item.added":
        _on_item_added(event=event, state=state)
    elif event_type == "response.output_text.delta":
        _on_text_delta(event=event, state=state)
    elif event_type == "response.function_call_arguments.delta":
        _on_function_delta(event=event, state=state)
    elif event_type == "response.function_call_arguments.done":
        _on_function_done(event=event, state=state)
    elif event_type == "response.output_item.done":
        _on_output_done(event=event, state=state)
    elif event_type in {"response.completed", "response.done"}:
        _on_response_done(event=event, state=state)
        return True
    return False


def _response_failed_error(*, event: dict[str, Any], profile_id: str) -> CodexUpstreamError:
    error_payload = event.get("response", {}).get("error", {})
    if isinstance(error_payload, dict) and error_payload.get("message"):
        message = str(error_payload["message"])
        return CodexUpstreamError(
            message,
            profile_id=profile_id,
            retriable=is_retryable_codex_error_message(message),
            account_unavailable=is_account_unavailable_message(message),
        )
    return CodexUpstreamError(
        "Codex response failed",
        profile_id=profile_id,
        retriable=True,
    )


def _on_item_added(*, event: dict[str, Any], state: dict[str, Any]) -> None:
    item = event.get("item", {})
    if not isinstance(item, dict):
        return
    item_type = str(item.get("type") or "")
    item_id = str(item.get("id") or "")
    if item_type == "message":
        current_text = AssistantTextItem(item_id=item_id or f"msg_{uuid.uuid4().hex[:8]}")
        state["response_items"].append(current_text)
        state["current_text"] = current_text
        state["current_tool"] = None
    elif item_type == "function_call":
        current_tool = ToolCallItem(
            call_id=str(item.get("call_id") or f"call_{uuid.uuid4().hex[:8]}"),
            item_id=item_id or f"fc_{uuid.uuid4().hex[:8]}",
            name=str(item.get("name") or ""),
            arguments_json=str(item.get("arguments") or "{}"),
        )
        state["response_items"].append(current_tool)
        state["current_tool"] = current_tool
        state["current_text"] = None


def _on_text_delta(*, event: dict[str, Any], state: dict[str, Any]) -> None:
    delta = event.get("delta")
    current_text = state.get("current_text")
    if isinstance(delta, str) and current_text is not None:
        current_text.text += delta


def _on_function_delta(*, event: dict[str, Any], state: dict[str, Any]) -> None:
    delta = event.get("delta")
    current_tool = state.get("current_tool")
    if not isinstance(delta, str) or current_tool is None:
        return
    current_tool.arguments_json += delta
    try:
        current_tool.arguments = json.loads(current_tool.arguments_json)
    except Exception:
        return


def _on_function_done(*, event: dict[str, Any], state: dict[str, Any]) -> None:
    current_tool = state.get("current_tool")
    arguments = event.get("arguments")
    if current_tool is None or not isinstance(arguments, str) or not arguments.strip():
        return
    current_tool.arguments_json = arguments
    try:
        current_tool.arguments = json.loads(arguments)
    except Exception:
        current_tool.arguments = {}


def _on_output_done(*, event: dict[str, Any], state: dict[str, Any]) -> None:
    item = event.get("item", {})
    if not isinstance(item, dict):
        return
    item_type = str(item.get("type") or "")
    if item_type == "message":
        _finalize_message(item=item, state=state)
    elif item_type == "function_call":
        _finalize_function(item=item, state=state)


def _finalize_message(*, item: dict[str, Any], state: dict[str, Any]) -> None:
    current_text = state.get("current_text")
    if current_text is None:
        return
    content_parts = item.get("content")
    if isinstance(content_parts, list):
        parts: list[str] = []
        for part in content_parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                parts.append(part["refusal"])
        if parts:
            current_text.text = "".join(parts).strip()
    state["current_text"] = None


def _finalize_function(*, item: dict[str, Any], state: dict[str, Any]) -> None:
    current_tool = state.get("current_tool")
    if current_tool is None:
        return
    arguments = item.get("arguments")
    if isinstance(arguments, str) and arguments.strip():
        current_tool.arguments_json = arguments
        try:
            current_tool.arguments = json.loads(arguments)
        except Exception:
            current_tool.arguments = {}
    state["current_tool"] = None


def _on_response_done(*, event: dict[str, Any], state: dict[str, Any]) -> None:
    response_payload = event.get("response", {})
    if not isinstance(response_payload, dict):
        return
    state["usage"] = response_payload.get("usage")
    status = str(response_payload.get("status") or "completed").strip().lower()
    if status in {"failed", "cancelled"}:
        state["stop_reason"] = "error"
    elif status == "incomplete":
        state["stop_reason"] = "length"
    else:
        state["stop_reason"] = "stop"
