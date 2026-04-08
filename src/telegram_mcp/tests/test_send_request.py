"""Unit tests for send_request validation and types."""

from __future__ import annotations

import unittest

from telegram_mcp.send_request import (
    validate_media,
    validate_message_text,
    validate_parse_mode,
)


class TestValidateMessageText(unittest.TestCase):
    def test_valid_text(self) -> None:
        self.assertIsNone(validate_message_text("hello"))

    def test_empty_text(self) -> None:
        result = validate_message_text("   ")
        self.assertIsNotNone(result)

    def test_too_long_text(self) -> None:
        result = validate_message_text("a" * 5000)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("4096", result)


class TestValidateParseMode(unittest.TestCase):
    def test_markdown(self) -> None:
        self.assertEqual(validate_parse_mode("markdown"), "markdown")

    def test_html(self) -> None:
        self.assertEqual(validate_parse_mode("html"), "html")

    def test_case_insensitive(self) -> None:
        self.assertEqual(validate_parse_mode("Markdown"), "markdown")

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            validate_parse_mode("bbcode")


class TestValidateMedia(unittest.TestCase):
    def test_valid_photo(self) -> None:
        media = validate_media({"type": "photo", "data": "aGVsbG8="})
        self.assertEqual(media.media_type, "photo")
        self.assertEqual(media.data, "aGVsbG8=")

    def test_valid_document_with_filename(self) -> None:
        media = validate_media(
            {
                "type": "document",
                "data": "aGVsbG8=",
                "filename": "test.pdf",
            }
        )
        self.assertEqual(media.media_type, "document")
        self.assertEqual(media.filename, "test.pdf")

    def test_invalid_type(self) -> None:
        with self.assertRaises(ValueError):
            validate_media({"type": "video", "data": "aGVsbG8="})

    def test_missing_data(self) -> None:
        with self.assertRaises(ValueError):
            validate_media({"type": "photo", "data": ""})

    def test_voice_type(self) -> None:
        media = validate_media({"type": "voice", "data": "aGVsbG8="})
        self.assertEqual(media.media_type, "voice")
