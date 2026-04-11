"""Compatibility facade for telegram_events service support helpers."""

import sys

from core.telegram_events.service import support as _support

sys.modules[__name__] = _support
