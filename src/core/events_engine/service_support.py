"""Compatibility facade for events_engine support symbols."""

import sys

from core.events_engine.service import support as _support

sys.modules[__name__] = _support
