from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from itertools import count
from typing import Any

JsonObject = dict[str, Any]


def generated_id(prefix: str, length: int = 8) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:length]}"


def value_or_generated_id(value: Any, prefix: str, length: int = 8) -> str:
    if value:
        return str(value)
    return generated_id(prefix, length)


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
            summary = "; ".join(
                f"{item.get('profile_id')}: {item.get('error')}" for item in attempts
            )
        else:
            summary = "no codex accounts available"
        super().__init__(summary)


def codex_response_to_dict(response: CodexModelResponse) -> JsonObject:
    serialized_items: list[JsonObject] = []
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


def codex_response_stream_events(response: CodexModelResponse) -> list[JsonObject]:
    response_id = generated_id("resp", 12)
    sequence_numbers = count(1)
    next_sequence_number = sequence_numbers.__next__

    events: list[JsonObject] = [
        {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "model": response.model,
                "status": "in_progress",
            },
            "sequence_number": next_sequence_number(),
        }
    ]
    append_response_output_events(events, response, response_id, next_sequence_number)
    append_response_terminal_events(events, response, response_id, next_sequence_number)
    return events


def append_response_output_events(
    events: list[JsonObject],
    response: CodexModelResponse,
    response_id: str,
    next_sequence_number: Any,
) -> None:
    output_index = 0
    for item in response.items:
        output_events = response_item_events(item, response_id, output_index, next_sequence_number)
        if output_events:
            events.extend(output_events)
            output_index += 1


def response_item_events(
    item: Any,
    response_id: str,
    output_index: int,
    next_sequence_number: Any,
) -> list[JsonObject]:
    if isinstance(item, AssistantTextItem):
        return assistant_text_item_events(item, response_id, output_index, next_sequence_number)
    if isinstance(item, ToolCallItem):
        return tool_call_item_events(item, response_id, output_index, next_sequence_number)
    return []


def assistant_text_item_events(
    item: AssistantTextItem,
    response_id: str,
    output_index: int,
    next_sequence_number: Any,
) -> list[JsonObject]:
    events: list[JsonObject] = [
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
            "sequence_number": next_sequence_number(),
        },
        {
            "type": "response.content_part.added",
            "response_id": response_id,
            "item_id": item.item_id,
            "output_index": output_index,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
            "sequence_number": next_sequence_number(),
        },
    ]
    if item.text:
        events.append(
            {
                "type": "response.output_text.delta",
                "response_id": response_id,
                "item_id": item.item_id,
                "output_index": output_index,
                "content_index": 0,
                "delta": item.text,
                "sequence_number": next_sequence_number(),
            }
        )
    events.extend(
        [
            {
                "type": "response.output_text.done",
                "response_id": response_id,
                "item_id": item.item_id,
                "output_index": output_index,
                "content_index": 0,
                "text": item.text,
                "sequence_number": next_sequence_number(),
            },
            {
                "type": "response.content_part.done",
                "response_id": response_id,
                "item_id": item.item_id,
                "output_index": output_index,
                "content_index": 0,
                "part": {"type": "output_text", "text": item.text, "annotations": []},
                "sequence_number": next_sequence_number(),
            },
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
                "sequence_number": next_sequence_number(),
            },
        ]
    )
    return events


def tool_call_item_events(
    item: ToolCallItem,
    response_id: str,
    output_index: int,
    next_sequence_number: Any,
) -> list[JsonObject]:
    events: list[JsonObject] = [
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
            "sequence_number": next_sequence_number(),
        },
    ]
    if item.arguments_json:
        events.append(
            {
                "type": "response.function_call_arguments.delta",
                "response_id": response_id,
                "item_id": item.item_id,
                "output_index": output_index,
                "delta": item.arguments_json,
                "sequence_number": next_sequence_number(),
            }
        )
    events.extend(
        [
            {
                "type": "response.function_call_arguments.done",
                "response_id": response_id,
                "item_id": item.item_id,
                "output_index": output_index,
                "arguments": item.arguments_json or "{}",
                "sequence_number": next_sequence_number(),
            },
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
                "sequence_number": next_sequence_number(),
            },
        ]
    )
    return events


def append_response_terminal_events(
    events: list[JsonObject],
    response: CodexModelResponse,
    response_id: str,
    next_sequence_number: Any,
) -> None:
    terminal_response = {
        "id": response_id,
        "object": "response",
        "status": codex_stop_reason_status(response.stop_reason),
        "usage": normalize_usage(response.usage),
        "model": response.model,
    }
    events.append(
        {
            "type": "response.completed",
            "response": terminal_response,
            "sequence_number": next_sequence_number(),
        }
    )
    events.append(
        {
            "type": "response.done",
            "response": terminal_response,
            "sequence_number": next_sequence_number(),
        }
    )


def codex_stop_reason_status(stop_reason: str) -> str:
    if stop_reason == "error":
        return "failed"
    if stop_reason == "length":
        return "incomplete"
    return "completed"


def codex_response_from_dict(payload: JsonObject) -> CodexModelResponse:
    items_payload = payload.get("items")
    if not isinstance(items_payload, list):
        raise RuntimeError("Expected llm_proxy Codex response payload to contain an items list")
    items: list[Any] = []
    for raw_item in items_payload:
        parsed_item = codex_item_from_payload(raw_item)
        if parsed_item is not None:
            items.append(parsed_item)
    return CodexModelResponse(
        items=items,
        stop_reason=str(payload.get("stop_reason") or "stop"),
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
        model=str(payload.get("model") or "").strip() or None,
    )


def codex_item_from_payload(raw_item: Any) -> AssistantTextItem | ToolCallItem | None:
    if not isinstance(raw_item, dict):
        return None

    item_type = str(raw_item.get("type") or "").strip()
    if item_type == "assistant_text":
        item_id = value_or_generated_id(raw_item.get("item_id"), "msg")
        return AssistantTextItem(
            item_id=item_id,
            text=str(raw_item.get("text") or ""),
        )
    if item_type != "tool_call":
        return None
    return tool_call_item_from_payload(raw_item)


def tool_call_item_from_payload(raw_item: JsonObject) -> ToolCallItem:
    arguments_json = raw_item.get("arguments_json")
    if not isinstance(arguments_json, str):
        arguments_json = json.dumps(raw_item.get("arguments") or {}, ensure_ascii=False)

    arguments = raw_item.get("arguments")
    if not isinstance(arguments, dict):
        try:
            arguments = json.loads(arguments_json)
        except Exception:
            arguments = {}

    return ToolCallItem(
        call_id=value_or_generated_id(raw_item.get("call_id"), "call"),
        item_id=value_or_generated_id(raw_item.get("item_id"), "fc"),
        name=str(raw_item.get("name") or "").strip(),
        arguments=arguments,
        arguments_json=arguments_json,
    )


def flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            part = flatten_content_list_item(item)
            if part:
                parts.append(part)
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        return flatten_content(list(content.values()))
    return str(content).strip()


def flatten_content_list_item(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return flatten_content_dict_item(item)
    return str(item).strip()


def flatten_content_dict_item(item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "")
    text_value = item.get("text")
    if item_type in {"text", "input_text", "output_text"} and isinstance(text_value, str):
        return text_value.strip()

    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    return flatten_content(list(item.values()))


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


def openai_messages_to_codex_input(messages: list[JsonObject]) -> list[JsonObject]:
    items: list[JsonObject] = []
    for index, message in enumerate(messages):
        items.extend(openai_message_to_codex_items(message=message, index=index))
    return items


def openai_message_to_codex_items(*, message: JsonObject, index: int) -> list[JsonObject]:
    role = str(message.get("role") or "").strip().lower()
    if role in {"system", "developer"}:
        return []

    content_text = flatten_content(message.get("content"))
    if role == "user":
        return user_openai_message_to_codex_items(content_text)
    if role == "assistant":
        return assistant_openai_message_to_codex_items(
            message=message,
            index=index,
            content_text=content_text,
        )
    if role == "tool":
        return tool_openai_message_to_codex_items(message=message, content_text=content_text)
    return []


def user_openai_message_to_codex_items(content_text: str) -> list[JsonObject]:
    if not content_text:
        return []
    return [{"role": "user", "content": [{"type": "input_text", "text": content_text}]}]


def assistant_openai_message_to_codex_items(
    *,
    message: JsonObject,
    index: int,
    content_text: str,
) -> list[JsonObject]:
    items: list[JsonObject] = []
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
    items.extend(assistant_tool_calls_to_codex_items(message=message, index=index))
    return items


def tool_openai_message_to_codex_items(
    *,
    message: JsonObject,
    content_text: str,
) -> list[JsonObject]:
    tool_call_id = str(message.get("tool_call_id") or "").strip()
    if not tool_call_id:
        return []
    return [
        {
            "type": "function_call_output",
            "call_id": tool_call_id,
            "output": content_text or "(empty tool result)",
        }
    ]


def assistant_tool_calls_to_codex_items(
    *,
    message: JsonObject,
    index: int,
) -> list[JsonObject]:
    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        return []

    converted: list[JsonObject] = []
    for tool_index, tool_call in enumerate(tool_calls):
        converted_item = assistant_tool_call_to_codex_item(
            tool_call=tool_call,
            index=index,
            tool_index=tool_index,
        )
        if converted_item is not None:
            converted.append(converted_item)
    return converted


def assistant_tool_call_to_codex_item(
    *,
    tool_call: Any,
    index: int,
    tool_index: int,
) -> JsonObject | None:
    if not isinstance(tool_call, dict):
        return None
    function = tool_call.get("function") or {}
    name = str(function.get("name") or "").strip()
    if not name:
        return None

    raw_arguments = function.get("arguments")
    arguments_json = (
        raw_arguments
        if isinstance(raw_arguments, str)
        else json.dumps(raw_arguments or {}, ensure_ascii=False)
    )
    call_id = str(tool_call.get("id") or f"call_{index}_{tool_index}")
    return {
        "type": "function_call",
        "id": f"fc_{index}_{tool_index}",
        "call_id": call_id,
        "name": name,
        "arguments": arguments_json,
    }


def normalize_responses_input_items(payload: JsonObject) -> list[JsonObject] | None:
    raw_items = payload.get("input_items")
    if isinstance(raw_items, list):
        return raw_items

    raw_input = payload.get("input")
    return normalize_responses_input(raw_input)


def normalize_responses_input(raw_input: Any) -> list[JsonObject] | None:
    if raw_input is None:
        return None
    if isinstance(raw_input, str):
        return normalize_responses_string_input(raw_input)
    if isinstance(raw_input, dict):
        return [raw_input]
    if not isinstance(raw_input, list):
        return None
    return normalize_responses_list_input(raw_input)


def normalize_responses_string_input(raw_input: str) -> list[JsonObject]:
    text = raw_input.strip()
    if not text:
        return []
    return [{"role": "user", "content": [{"type": "input_text", "text": text}]}]


def normalize_responses_list_input(raw_input: list[Any]) -> list[JsonObject]:
    normalized: list[JsonObject] = []
    for item in raw_input:
        normalized_item = normalize_responses_list_item(item)
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def normalize_responses_list_item(item: Any) -> JsonObject | None:
    if isinstance(item, dict):
        return item
    text = flatten_content(item)
    if not text:
        return None
    return {"role": "user", "content": [{"type": "input_text", "text": text}]}


def openai_tools_to_codex(
    tools_payload: list[JsonObject] | None,
    tool_choice: Any,
) -> list[JsonObject] | None:
    if not isinstance(tools_payload, list) or not tools_payload:
        return None
    if tool_choice == "none":
        return None

    selected_name = selected_tool_name(tool_choice)
    converted: list[JsonObject] = []
    for entry in tools_payload:
        converted_item = openai_tool_to_codex_tool(entry, selected_name)
        if converted_item is not None:
            converted.append(converted_item)
    return converted or None


def selected_tool_name(tool_choice: Any) -> str | None:
    if not isinstance(tool_choice, dict):
        return None
    function = tool_choice.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def openai_tool_to_codex_tool(entry: Any, selected_name: str | None) -> JsonObject | None:
    if not isinstance(entry, dict) or entry.get("type") != "function":
        return None
    function = entry.get("function") or {}
    name = str(function.get("name") or "").strip()
    if not name:
        return None
    if selected_name and name != selected_name:
        return None

    return {
        "type": "function",
        "name": name,
        "description": str(function.get("description") or "").strip(),
        "parameters": function.get("parameters") or {"type": "object", "properties": {}},
        "strict": bool(function.get("strict", False)),
    }


def codex_tools_to_openai_tools(
    tools_payload: list[JsonObject] | None,
) -> list[JsonObject] | None:
    if not isinstance(tools_payload, list) or not tools_payload:
        return None
    converted: list[JsonObject] = []
    for entry in tools_payload:
        converted_item = codex_tool_to_openai_tool(entry)
        if converted_item is not None:
            converted.append(converted_item)
    return converted or None


def codex_tool_to_openai_tool(entry: Any) -> JsonObject | None:
    if not isinstance(entry, dict) or entry.get("type") != "function":
        return None
    return {
        "type": "function",
        "function": {
            "name": str(entry.get("name") or "").strip(),
            "description": str(entry.get("description") or "").strip(),
            "parameters": entry.get("parameters") or {"type": "object", "properties": {}},
            "strict": bool(entry.get("strict", False)),
        },
    }


def codex_input_items_to_openai_messages(input_items: list[JsonObject]) -> list[JsonObject]:
    messages: list[JsonObject] = []
    for item in input_items:
        codex_input_item_to_openai_messages(item=item, messages=messages)
    return messages


def codex_input_item_to_openai_messages(*, item: Any, messages: list[JsonObject]) -> None:
    if not isinstance(item, dict):
        return

    role = str(item.get("role") or "").strip().lower()
    item_type = str(item.get("type") or "").strip().lower()
    if role == "user":
        append_user_message(item=item, messages=messages)
        return
    if item_type == "message" and role == "assistant":
        append_assistant_message(item=item, messages=messages)
        return
    if item_type == "function_call":
        append_function_call_message(item=item, messages=messages)
        return
    if item_type == "function_call_output":
        append_tool_output_message(item=item, messages=messages)


def append_user_message(*, item: JsonObject, messages: list[JsonObject]) -> None:
    text = flatten_content(item.get("content"))
    if text:
        messages.append({"role": "user", "content": text})


def append_assistant_message(*, item: JsonObject, messages: list[JsonObject]) -> None:
    text = flatten_content(item.get("content"))
    messages.append({"role": "assistant", "content": text or None})


def append_function_call_message(*, item: JsonObject, messages: list[JsonObject]) -> None:
    function_call = {
        "id": value_or_generated_id(item.get("call_id"), "call"),
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
        return
    messages.append({"role": "assistant", "content": None, "tool_calls": [function_call]})


def append_tool_output_message(*, item: JsonObject, messages: list[JsonObject]) -> None:
    messages.append(
        {
            "role": "tool",
            "tool_call_id": str(item.get("call_id") or "").strip(),
            "content": flatten_content(item.get("output")) or "(empty tool result)",
        }
    )


def normalize_usage(usage: JsonObject | None) -> JsonObject:
    payload = usage if isinstance(usage, dict) else {}
    token_counts = usage_token_counts(payload)
    token_details = usage_token_details(payload)
    token_total = token_counts[0] + token_counts[1]
    total_tokens = int(payload.get("total_tokens") or token_total)
    return {
        "prompt_tokens": token_counts[0],
        "completion_tokens": token_counts[1],
        "total_tokens": total_tokens,
        "prompt_tokens_details": token_details[0],
        "completion_tokens_details": token_details[1],
        "input_tokens": token_counts[0],
        "output_tokens": token_counts[1],
        "input_tokens_details": token_details[0],
        "output_tokens_details": token_details[1],
    }


def usage_token_counts(payload: JsonObject) -> tuple[int, int]:
    prompt_tokens = int(payload.get("input_tokens") or payload.get("prompt_tokens") or 0)
    completion_tokens = int(payload.get("output_tokens") or payload.get("completion_tokens") or 0)
    return prompt_tokens, completion_tokens


def usage_token_details(payload: JsonObject) -> tuple[Any, Any]:
    prompt_details = (
        payload.get("input_tokens_details")
        or payload.get("prompt_tokens_details")
        or {"cached_tokens": 0}
    )
    completion_details = (
        payload.get("output_tokens_details")
        or payload.get("completion_tokens_details")
        or {"reasoning_tokens": 0}
    )
    return prompt_details, completion_details


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


def tool_calls_to_openai(tool_calls: list[ToolCallItem]) -> list[JsonObject]:
    converted: list[JsonObject] = []
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


def build_chat_completion_response(*, response: CodexModelResponse, model: str) -> JsonObject:
    effective_model = response.model or model
    message: JsonObject = {
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


def completion_stream_chunks(response_payload: JsonObject) -> list[JsonObject]:
    chunk_context = completion_stream_context(response_payload)
    tool_calls = completion_tool_calls(chunk_context)
    if isinstance(tool_calls, list) and tool_calls:
        return tool_call_stream_chunks(chunk_context, tool_calls)
    return content_stream_chunks(chunk_context)


def completion_tool_calls(chunk_context: JsonObject) -> Any:
    message = chunk_context["choice"].get("message") or {}
    return message.get("tool_calls") or []


def tool_call_stream_chunks(chunk_context: JsonObject, tool_calls: list[Any]) -> list[JsonObject]:
    chunks: list[JsonObject] = [build_completion_stream_chunk(chunk_context, {"role": "assistant"})]
    for index, tool_call in enumerate(tool_calls):
        chunks.append(
            build_completion_stream_chunk(chunk_context, tool_call_delta(tool_call, index))
        )
    finish_reason = chunk_context["choice"].get("finish_reason")
    chunks.append(build_completion_stream_chunk(chunk_context, {}, finish_reason or "tool_calls"))
    return chunks


def tool_call_delta(tool_call: Any, index: int) -> JsonObject:
    function = tool_call.get("function") or {}
    return {
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


def content_stream_chunks(chunk_context: JsonObject) -> list[JsonObject]:
    message = chunk_context["choice"].get("message") or {}
    finish_reason = chunk_context["choice"].get("finish_reason")
    content = str(message.get("content") or "")
    chunks = [build_completion_stream_chunk(chunk_context, {"role": "assistant"})]
    if content:
        chunks.append(build_completion_stream_chunk(chunk_context, {"content": content}))
    chunks.append(build_completion_stream_chunk(chunk_context, {}, finish_reason or "stop"))
    return chunks


def completion_stream_context(response_payload: JsonObject) -> JsonObject:
    completion_id = value_or_generated_id(response_payload.get("id"), "chatcmpl", 12)
    return {
        "choice": (response_payload.get("choices") or [{}])[0],
        "created": int(response_payload.get("created") or time.time()),
        "model": str(response_payload.get("model") or ""),
        "completion_id": completion_id,
    }


def build_completion_stream_chunk(
    chunk_context: JsonObject,
    delta: JsonObject,
    finish: str | None = None,
) -> JsonObject:
    return {
        "id": chunk_context["completion_id"],
        "object": "chat.completion.chunk",
        "created": chunk_context["created"],
        "model": chunk_context["model"],
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish,
            }
        ],
    }


def openai_chat_payload_to_codex_response(payload: JsonObject) -> CodexModelResponse:
    choice, message = openai_choice_and_message(payload)
    items: list[Any] = []
    content = flatten_content(message.get("content"))
    if content:
        items.append(AssistantTextItem(item_id=generated_id("msg"), text=content))
    items.extend(openai_tool_calls_to_codex_items(message))
    return CodexModelResponse(
        items=items,
        stop_reason=stop_reason_from_openai_finish_reason(choice.get("finish_reason")),
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
        model=str(payload.get("model") or "").strip() or None,
    )


def openai_choice_and_message(payload: JsonObject) -> tuple[JsonObject, JsonObject]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Fallback returned no choices")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Fallback returned invalid choice.message")
    return choice, message


def openai_tool_calls_to_codex_items(message: JsonObject) -> list[ToolCallItem]:
    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        return []

    converted: list[ToolCallItem] = []
    for index, tool_call in enumerate(tool_calls):
        tool_item = openai_tool_call_to_codex_item(tool_call=tool_call, index=index)
        if tool_item is not None:
            converted.append(tool_item)
    return converted


def openai_tool_call_to_codex_item(*, tool_call: Any, index: int) -> ToolCallItem | None:
    if not isinstance(tool_call, dict):
        return None
    function = tool_call.get("function") or {}
    raw_arguments = function.get("arguments")
    arguments_json = (
        raw_arguments
        if isinstance(raw_arguments, str)
        else json.dumps(raw_arguments or {}, ensure_ascii=False)
    )
    try:
        arguments = json.loads(arguments_json)
    except Exception:
        arguments = {}

    return ToolCallItem(
        call_id=value_or_generated_id(tool_call.get("id"), f"call_{index}", 6),
        item_id=generated_id("fc"),
        name=str(function.get("name") or "").strip(),
        arguments=arguments,
        arguments_json=arguments_json,
    )
