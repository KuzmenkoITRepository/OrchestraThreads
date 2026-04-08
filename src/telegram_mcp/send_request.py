"""Typed send request and media payload for the canonical send pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

_MAX_TEXT_LENGTH = 4096
_MAX_PHOTO_BYTES = 10 * 1024 * 1024
_MAX_DOCUMENT_BYTES = 50 * 1024 * 1024

ParseMode = Literal["markdown", "html"] | None
MediaType = Literal["photo", "document", "voice"]
MediaSource = Literal["base64", "file"]


@dataclass(frozen=True)
class MediaPayload:
    """Typed media attachment for a send request."""

    media_type: MediaType
    data: str
    source: MediaSource = "base64"
    filename: str | None = None


@dataclass(frozen=True)
class SendRequest:
    """Canonical typed send request built from MCP tool arguments."""

    message: str
    recipient: str | None = None
    parse_mode: ParseMode = None
    reply_to_message_id: int | None = None
    media: MediaPayload | None = None


def validate_message_text(text: str) -> str | None:
    """Return an error string if text is invalid, else None."""
    if not text.strip():
        return "message must not be empty or whitespace-only"
    if len(text) > _MAX_TEXT_LENGTH:
        return f"message must be {_MAX_TEXT_LENGTH} characters or fewer"
    return None


_PARSE_MODES: MappingProxyType[str, ParseMode] = MappingProxyType(
    {"markdown": "markdown", "html": "html"}
)


def validate_parse_mode(raw: str) -> ParseMode:
    """Validate and normalize a parse_mode string."""
    result = _PARSE_MODES.get(raw.strip().lower())
    if result is None:
        raise ValueError(f"Invalid parse_mode '{raw}'. Allowed: markdown, html")
    return result


_MEDIA_TYPES: MappingProxyType[str, MediaType] = MappingProxyType(
    {
        "photo": "photo",
        "document": "document",
        "voice": "voice",
    }
)


def validate_media(media_dict: dict[str, object]) -> MediaPayload:
    """Validate a raw media dict and return a typed MediaPayload."""
    raw_type = str(media_dict.get("type") or "").strip().lower()
    media_type = _MEDIA_TYPES.get(raw_type)
    if media_type is None:
        raise ValueError(f"Invalid media type '{raw_type}'. Allowed: photo, document, voice")
    raw_data = str(media_dict.get("data") or "").strip()
    raw_path = str(media_dict.get("path") or "").strip()
    if raw_path:
        return MediaPayload(
            media_type=media_type,
            data=raw_path,
            source="file",
            filename=raw_path.rsplit("/", 1)[-1],
        )
    if not raw_data:
        raise ValueError("media.data or media.path is required")
    _check_media_size(raw_type, raw_data)
    filename = str(media_dict.get("filename") or "").strip() or None
    return MediaPayload(media_type=media_type, data=raw_data, filename=filename)


def _check_media_size(media_type: str, data: str) -> None:
    byte_count = len(data) * 3 // 4
    if media_type == "photo" and byte_count > _MAX_PHOTO_BYTES:
        raise ValueError(f"Photo too large: {byte_count} bytes (max {_MAX_PHOTO_BYTES})")
    if media_type in {"document", "voice"} and byte_count > _MAX_DOCUMENT_BYTES:
        raise ValueError(f"File too large: {byte_count} bytes (max {_MAX_DOCUMENT_BYTES})")
