from __future__ import annotations

from core.orchestra_agents.backends.agent_mux.normalization import sanitize_reply_text
from core.orchestra_agents.backends.sgr.llm.client import (
    SGRLLMClientCore as _SGRLLMClientCore,
)
from core.orchestra_agents.backends.sgr.llm.client import (
    _append_and_should_stop as _append_and_should_stop,
)
from core.orchestra_agents.backends.sgr.llm.client import (
    _decoded_stream_line as _decoded_stream_line,
)
from core.orchestra_agents.backends.sgr.llm.client import _is_stream_done as _is_stream_done
from core.orchestra_agents.backends.sgr.llm.client import (
    _payload_model as _payload_model,
)
from core.orchestra_agents.backends.sgr.llm.client import (
    _read_stream_lines as _read_stream_lines,
)


class SGRLLMClient(_SGRLLMClientCore):
    def __init__(
        self,
        agent_slug: str,
        route_policy: str,
        timeout_seconds: float | None,
    ) -> None:
        super().__init__(
            agent_slug=agent_slug,
            route_policy=route_policy,
            timeout_seconds=timeout_seconds,
            sanitize_reply_text=sanitize_reply_text,
        )
