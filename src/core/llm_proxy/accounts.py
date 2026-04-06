from __future__ import annotations

import importlib
import sys

sys.modules[__name__] = importlib.import_module("core.llm_proxy._accounts_impl")
