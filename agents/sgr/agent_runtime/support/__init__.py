"""SGR runtime support — settings, outcomes, and prompt construction."""

from __future__ import annotations

from agents.sgr.agent_runtime.support.outcomes import (
    AgentTurnOutcome as AgentTurnOutcome,
)
from agents.sgr.agent_runtime.support.outcomes import (
    ParsedToolCall as ParsedToolCall,
)
from agents.sgr.agent_runtime.support.outcomes import (
    ToolExecutionOutcome as ToolExecutionOutcome,
)
from agents.sgr.agent_runtime.support.outcomes import (
    handle_direct_text_retry as handle_direct_text_retry,
)
from agents.sgr.agent_runtime.support.outcomes import (
    parse_tool_call as parse_tool_call,
)
from agents.sgr.agent_runtime.support.prompts import (
    operational_notes_text as operational_notes_text,
)
from agents.sgr.agent_runtime.support.prompts import (
    tool_runtime_rules_text as tool_runtime_rules_text,
)
from agents.sgr.agent_runtime.support.prompts import (
    wake_up_block as wake_up_block,
)
from agents.sgr.agent_runtime.support.settings import (
    SGRRuntimeSettings as SGRRuntimeSettings,
)
from agents.sgr.agent_runtime.support.settings import (
    normalize_int as normalize_int,
)
from agents.sgr.agent_runtime.support.settings import (
    normalize_optional_str as normalize_optional_str,
)
from agents.sgr.agent_runtime.support.settings import (
    thread_client_timeout_seconds as thread_client_timeout_seconds,
)
