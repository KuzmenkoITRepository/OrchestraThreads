from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssistantTextItem:
    item_id: str
    text: str = ""


@dataclass
class ToolCallItem:
    call_id: str
    item_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_json: str = "{}"


@dataclass
class CodexModelResponse:
    items: list[Any]
    stop_reason: str
    usage: dict[str, Any] | None = None
    model: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(
            item.text.strip()
            for item in self.items
            if isinstance(item, AssistantTextItem) and item.text.strip()
        ).strip()

    @property
    def tool_calls(self) -> list[ToolCallItem]:
        return [item for item in self.items if isinstance(item, ToolCallItem)]


class CodexUpstreamError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        profile_id: str | None = None,
        status_code: int | None = None,
        retriable: bool = False,
        account_unavailable: bool = False,
    ) -> None:
        super().__init__(message)
        self.profile_id = profile_id
        self.status_code = status_code
        self.retriable = retriable
        self.account_unavailable = account_unavailable

    @property
    def should_try_next_profile(self) -> bool:
        return self.account_unavailable or self.retriable


class AllCodexAccountsUnavailable(RuntimeError):
    def __init__(self, attempts: list[dict[str, Any]]) -> None:
        self.attempts = attempts
        if attempts:
            summary = "; ".join(f"{item.get('profile_id')}: {item.get('error')}" for item in attempts)
        else:
            summary = "no codex accounts available"
        super().__init__(summary)


def codex_response_to_dict(response: CodexModelResponse) -> dict[str, Any]:
    serialized_items: list[dict[str, Any]] = []
    for item in response.items:
        if isinstance(item, AssistantTextItem):
            serialized_items.append(
                {
                    "type": "assistant_text",
                    "item_id": item.item_id,
                    "text": item.text,
                }
            )
        elif isinstance(item, ToolCallItem):
            serialized_items.append(
                {
                    "type": "tool_call",
                    "call_id": item.call_id,
                    "item_id": item.item_id,
                    "name": item.name,
                    "arguments": item.arguments,
                    "arguments_json": item.arguments_json,
                }
            )
    return {
        "items": serialized_items,
        "stop_reason": response.stop_reason,
        "usage": normalize_usage(response.usage),
        "model": response.model,
    }


def codex_response_stream_events(response: CodexModelResponse) -> list[dict[str, Any]]:
    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    sequence_number = 0

    def _next_seq() -> int:
        nonlocal sequence_number
        sequence_number += 1
        return sequence_number

    events: list[dict[str, Any]] = [
        {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "model": response.model,
                "status": "in_progress",
            },
            "sequence_number": _next_seq(),
        }
    ]
    output_index = 0
    for item in response.items:
        if isinstance(item, AssistantTextItem):
            events.append(
                {
                    "type": "response.output_item.added",
                    "response_id": response_id,
                    "output_index": output_index,
                    "item": {
                        "id": item.item_id,
                        "type": "message",
                        "status": "in_progress",
                        "role": "assistant",
                        "content": [],
                    },
                    "sequence_number": _next_seq(),
                }
            )
            events.append(
                {
                    "type": "response.content_part.added",
                    "response_id": response_id,
                    "item_id": item.item_id,
                    "output_index": output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                    "sequence_number": _next_seq(),
                }
            )
            if item.text:
                events.append(
                    {
                        "type": "response.output_text.delta",
                        "response_id": response_id,
                        "item_id": item.item_id,
                        "output_index": output_index,
                        "content_index": 0,
                        "delta": item.text,
                        "sequence_number": _next_seq(),
                    }
                )
            events.append(
                {
                    "type": "response.output_text.done",
                    "response_id": response_id,
                    "item_id": item.item_id,
                    "output_index": output_index,
                    "content_index": 0,
                    "text": item.text,
                    "sequence_number": _next_seq(),
                }
            )
            events.append(
                {
                    "type": "response.content_part.done",
                    "response_id": response_id,
                    "item_id": item.item_id,
                    "output_index": output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": item.text, "annotations": []},
                    "sequence_number": _next_seq(),
                }
            )
            events.append(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "id": item.item_id,
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": item.text, "annotations": []}],
                    },
                    "response_id": response_id,
                    "output_index": output_index,
                    "sequence_number": _next_seq(),
                }
            )
            output_index += 1
            continue
        if isinstance(item, ToolCallItem):
            events.append(
                {
                    "type": "response.output_item.added",
                    "response_id": response_id,
                    "output_index": output_index,
                    "item": {
                        "type": "function_call",
                        "id": item.item_id,
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": "",
                    },
                    "sequence_number": _next_seq(),
                }
            )
            if item.arguments_json:
                events.append(
                    {
                        "type": "response.function_call_arguments.delta",
                        "response_id": response_id,
                        "item_id": item.item_id,
                        "output_index": output_index,
                        "delta": item.arguments_json,
                        "sequence_number": _next_seq(),
                    }
                )
            events.append(
                {
                    "type": "response.function_call_arguments.done",
                    "response_id": response_id,
                    "item_id": item.item_id,
                    "output_index": output_index,
                    "arguments": item.arguments_json or "{}",
                    "sequence_number": _next_seq(),
                }
            )
            events.append(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "function_call",
                        "id": item.item_id,
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": item.arguments_json or "{}",
                    },
                    "response_id": response_id,
                    "output_index": output_index,
                    "sequence_number": _next_seq(),
                }
            )
            output_index += 1
    status = "completed"
    if response.stop_reason == "error":
        status = "failed"
    elif response.stop_reason == "length":
        status = "incomplete"
    events.append(
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "object": "response",
                "status": status,
                "usage": normalize_usage(response.usage),
                "model": response.model,
            },
            "sequence_number": _next_seq(),
        }
    )
    events.append(
        {
            "type": "response.done",
            "response": {
                "id": response_id,
                "object": "response",
                "status": status,
                "usage": normalize_usage(response.usage),
                "model": response.model,
            },
            "sequence_number": _next_seq(),
        }
    )
    return events


def codex_response_from_dict(payload: dict[str, Any]) -> CodexModelResponse:
    items_payload = payload.get("items")
    if not isinstance(items_payload, list):
        raise RuntimeError("Expected llm_proxy Codex response payload to contain an items list")
    items: list[Any] = []
    for raw_item in items_payload:
        if not isinstance(raw_item, dict):
            continue
        item_type = str(raw_item.get("type") or "").strip()
        if item_type == "assistant_text":
            items.append(
                AssistantTextItem(
                    item_id=str(raw_item.get("item_id") or f"msg_{uuid.uuid4().hex[:8]}"),
                    text=str(raw_item.get("text") or ""),
                )
            )
            continue
        if item_type != "tool_call":
            continue
        arguments_json = raw_item.get("arguments_json")
        if not isinstance(arguments_json, str):
            arguments_json = json.dumps(raw_item.get("arguments") or {}, ensure_ascii=False)
        arguments = raw_item.get("arguments")
        if not isinstance(arguments, dict):
            try:
                arguments = json.loads(arguments_json)
            except Exception:
                arguments = {}
        items.append(
            ToolCallItem(
                call_id=str(raw_item.get("call_id") or f"call_{uuid.uuid4().hex[:8]}"),
                item_id=str(raw_item.get("item_id") or f"fc_{uuid.uuid4().hex[:8]}"),
                name=str(raw_item.get("name") or "").strip(),
                arguments=arguments,
                arguments_json=arguments_json,
            )
        )
    return CodexModelResponse(
        items=items,
        stop_reason=str(payload.get("stop_reason") or "stop"),
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
        model=str(payload.get("model") or "").strip() or None,
    )


def flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item.strip())
                continue
            if isinstance(item, dict):
                item_type = str(item.get("type") or "")
                if item_type in {"text", "input_text", "output_text"}:
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value.strip())
                    continue
                if isinstance(item.get("content"), str) and item["content"].strip():
                    parts.append(item["content"].strip())
                    continue
                nested_text = flatten_content(list(item.values()))
                if nested_text:
                    parts.append(nested_text)
                continue
            parts.append(str(item).strip())
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        return flatten_content(list(content.values()))
    return str(content).strip()


def build_instructions(messages: list[dict[str, Any]], fallback: str) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        if role not in {"system", "developer"}:
            continue
        text = flatten_content(message.get("content"))
        if text:
            parts.append(text)
    if not parts:
        return fallback
    return "\n\n".join(parts).strip()


def openai_messages_to_codex_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        role = str(message.get("role") or "").strip().lower()
        if role in {"system", "developer"}:
            continue
        content_text = flatten_content(message.get("content"))
        if role == "user":
            if content_text:
                items.append(
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": content_text}],
                    }
                )
            continue
        if role == "assistant":
            if content_text:
                items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": content_text, "annotations": []}],
                        "status": "completed",
                        "id": f"msg_{index}",
                    }
                )
            tool_calls = message.get("tool_calls") or []
            if isinstance(tool_calls, list):
                for tool_index, tool_call in enumerate(tool_calls):
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function") or {}
                    name = str(function.get("name") or "").strip()
                    if not name:
                        continue
                    raw_arguments = function.get("arguments")
                    if isinstance(raw_arguments, str):
                        arguments_json = raw_arguments
                    else:
                        arguments_json = json.dumps(raw_arguments or {}, ensure_ascii=False)
                    call_id = str(tool_call.get("id") or f"call_{index}_{tool_index}")
                    items.append(
                        {
                            "type": "function_call",
                            "id": f"fc_{index}_{tool_index}",
                            "call_id": call_id,
                            "name": name,
                            "arguments": arguments_json,
                        }
                    )
            continue
        if role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "").strip()
            if tool_call_id:
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call_id,
                        "output": content_text or "(empty tool result)",
                    }
                )
    return items


def normalize_responses_input_items(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    raw_items = payload.get("input_items")
    if isinstance(raw_items, list):
        return raw_items

    raw_input = payload.get("input")
    if raw_input is None:
        return None
    if isinstance(raw_input, str):
        text = raw_input.strip()
        if not text:
            return []
        return [{"role": "user", "content": [{"type": "input_text", "text": text}]}]
    if isinstance(raw_input, dict):
        return [raw_input]
    if not isinstance(raw_input, list):
        return None

    normalized: list[dict[str, Any]] = []
    for item in raw_input:
        if isinstance(item, dict):
            normalized.append(item)
            continue
        text = flatten_content(item)
        if not text:
            continue
        normalized.append({"role": "user", "content": [{"type": "input_text", "text": text}]})
    return normalized


def openai_tools_to_codex(
    tools_payload: list[dict[str, Any]] | None,
    tool_choice: Any,
) -> list[dict[str, Any]] | None:
    if not isinstance(tools_payload, list) or not tools_payload:
        return None
    selected_name: str | None = None
    if tool_choice == "none":
        return None
    if isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name.strip():
                selected_name = name.strip()
    converted: list[dict[str, Any]] = []
    for entry in tools_payload:
        if not isinstance(entry, dict) or entry.get("type") != "function":
            continue
        function = entry.get("function") or {}
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        if selected_name and name != selected_name:
            continue
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": str(function.get("description") or "").strip(),
                "parameters": function.get("parameters") or {"type": "object", "properties": {}},
                "strict": bool(function.get("strict", False)),
            }
        )
    return converted or None


def codex_tools_to_openai_tools(tools_payload: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not isinstance(tools_payload, list) or not tools_payload:
        return None
    converted: list[dict[str, Any]] = []
    for entry in tools_payload:
        if not isinstance(entry, dict) or entry.get("type") != "function":
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": str(entry.get("name") or "").strip(),
                    "description": str(entry.get("description") or "").strip(),
                    "parameters": entry.get("parameters") or {"type": "object", "properties": {}},
                    "strict": bool(entry.get("strict", False)),
                },
            }
        )
    return converted or None


def codex_input_items_to_openai_messages(input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in input_items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        item_type = str(item.get("type") or "").strip().lower()
        if role == "user":
            text = flatten_content(item.get("content"))
            if text:
                messages.append({"role": "user", "content": text})
            continue
        if item_type == "message" and role == "assistant":
            text = flatten_content(item.get("content"))
            messages.append({"role": "assistant", "content": text or None})
            continue
        if item_type == "function_call":
            function_call = {
                "id": str(item.get("call_id") or f"call_{uuid.uuid4().hex[:8]}"),
                "type": "function",
                "function": {
                    "name": str(item.get("name") or "").strip(),
                    "arguments": str(item.get("arguments") or "{}"),
                },
            }
            if messages and messages[-1].get("role") == "assistant":
                tool_calls = messages[-1].setdefault("tool_calls", [])
                if isinstance(tool_calls, list):
                    tool_calls.append(function_call)
                if "content" not in messages[-1]:
                    messages[-1]["content"] = None
            else:
                messages.append({"role": "assistant", "content": None, "tool_calls": [function_call]})
            continue
        if item_type == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(item.get("call_id") or "").strip(),
                    "content": flatten_content(item.get("output")) or "(empty tool result)",
                }
            )
    return messages


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    payload = usage if isinstance(usage, dict) else {}
    prompt_tokens = int(payload.get("input_tokens") or payload.get("prompt_tokens") or 0)
    completion_tokens = int(payload.get("output_tokens") or payload.get("completion_tokens") or 0)
    total_tokens = int(payload.get("total_tokens") or (prompt_tokens + completion_tokens))
    prompt_details = payload.get("input_tokens_details") or payload.get("prompt_tokens_details") or {"cached_tokens": 0}
    completion_details = payload.get("output_tokens_details") or payload.get("completion_tokens_details") or {
        "reasoning_tokens": 0
    }
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens_details": prompt_details,
        "completion_tokens_details": completion_details,
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "input_tokens_details": prompt_details,
        "output_tokens_details": completion_details,
    }


def finish_reason_from_response(response: CodexModelResponse) -> str:
    if response.tool_calls:
        return "tool_calls"
    if response.stop_reason == "length":
        return "length"
    return "stop"


def stop_reason_from_openai_finish_reason(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"tool_calls", "function_call"}:
        return "tool_use"
    if normalized == "length":
        return "length"
    if normalized in {"content_filter", "error"}:
        return "error"
    return "stop"


def tool_calls_to_openai(tool_calls: list[ToolCallItem]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for call in tool_calls:
        converted.append(
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments_json,
                },
            }
        )
    return converted


def build_chat_completion_response(*, response: CodexModelResponse, model: str) -> dict[str, Any]:
    effective_model = response.model or model
    message: dict[str, Any] = {
        "role": "assistant",
        "content": response.text or None,
    }
    if response.tool_calls:
        message["tool_calls"] = tool_calls_to_openai(response.tool_calls)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": effective_model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason_from_response(response),
            }
        ],
        "usage": normalize_usage(response.usage),
    }


def completion_stream_chunks(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    choice = (response_payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    finish_reason = choice.get("finish_reason")
    created = int(response_payload.get("created") or time.time())
    model = str(response_payload.get("model") or "")
    completion_id = str(response_payload.get("id") or f"chatcmpl-{uuid.uuid4().hex[:12]}")

    def base_chunk(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
        return {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish,
                }
            ],
        }

    tool_calls = message.get("tool_calls") or []
    if isinstance(tool_calls, list) and tool_calls:
        stream_chunks: list[dict[str, Any]] = [base_chunk({"role": "assistant"})]
        for index, tool_call in enumerate(tool_calls):
            function = tool_call.get("function") or {}
            stream_chunks.append(
                base_chunk(
                    {
                        "tool_calls": [
                            {
                                "index": index,
                                "id": tool_call.get("id"),
                                "type": tool_call.get("type", "function"),
                                "function": {
                                    "name": function.get("name"),
                                    "arguments": function.get("arguments", "{}"),
                                },
                            }
                        ]
                    }
                )
            )
        stream_chunks.append(base_chunk({}, finish_reason or "tool_calls"))
        return stream_chunks
    content = str(message.get("content") or "")
    chunks = [base_chunk({"role": "assistant"})]
    if content:
        chunks.append(base_chunk({"content": content}))
    chunks.append(base_chunk({}, finish_reason or "stop"))
    return chunks


def openai_chat_payload_to_codex_response(payload: dict[str, Any]) -> CodexModelResponse:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Fallback returned no choices")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Fallback returned invalid choice.message")
    items: list[Any] = []
    content = flatten_content(message.get("content"))
    if content:
        items.append(AssistantTextItem(item_id=f"msg_{uuid.uuid4().hex[:8]}", text=content))
    tool_calls = message.get("tool_calls") or []
    if isinstance(tool_calls, list):
        for index, tool_call in enumerate(tool_calls):
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            raw_arguments = function.get("arguments")
            if isinstance(raw_arguments, str):
                arguments_json = raw_arguments
            else:
                arguments_json = json.dumps(raw_arguments or {}, ensure_ascii=False)
            arguments: dict[str, Any]
            try:
                arguments = json.loads(arguments_json)
            except Exception:
                arguments = {}
            items.append(
                ToolCallItem(
                    call_id=str(tool_call.get("id") or f"call_{index}_{uuid.uuid4().hex[:6]}"),
                    item_id=f"fc_{uuid.uuid4().hex[:8]}",
                    name=str(function.get("name") or "").strip(),
                    arguments=arguments,
                    arguments_json=arguments_json,
                )
            )
    return CodexModelResponse(
        items=items,
        stop_reason=stop_reason_from_openai_finish_reason(choice.get("finish_reason")),
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
        model=str(payload.get("model") or "").strip() or None,
    )
