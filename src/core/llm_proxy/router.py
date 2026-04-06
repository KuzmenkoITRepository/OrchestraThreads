from __future__ import annotations

import importlib
from typing import Any, cast

_router_runtime = cast(Any, importlib.import_module("core.llm_proxy.router_runtime"))
UnifiedLLMRouter = _router_runtime.UnifiedLLMRouter
CodexOAuthTransport = _router_runtime.CodexOAuthTransport
