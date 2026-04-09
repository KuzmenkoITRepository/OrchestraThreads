"""SGR runtime support — settings, outcomes, and prompt construction."""

from __future__ import annotations

from core.orchestra_agents.backends.sgr.support.event_metadata import (
    extract_event_metadata as extract_event_metadata,
)
from core.orchestra_agents.backends.sgr.support.event_metadata import (
    metadata_summary as metadata_summary,
)
from core.orchestra_agents.backends.sgr.support.outcomes import (
    AgentTurnOutcome as AgentTurnOutcome,
)
from core.orchestra_agents.backends.sgr.support.outcomes import (
    ParsedToolCall as ParsedToolCall,
)
from core.orchestra_agents.backends.sgr.support.outcomes import (
    ToolExecutionOutcome as ToolExecutionOutcome,
)
from core.orchestra_agents.backends.sgr.support.outcomes import (
    handle_direct_text_retry as handle_direct_text_retry,
)
from core.orchestra_agents.backends.sgr.support.outcomes import (
    parse_tool_call as parse_tool_call,
)
from core.orchestra_agents.backends.sgr.support.prompt_context import (
    operational_notes_text as operational_notes_text,
)
from core.orchestra_agents.backends.sgr.support.prompts import (
    tool_runtime_rules_text as tool_runtime_rules_text,
)
from core.orchestra_agents.backends.sgr.support.prompts import (
    wake_up_block as wake_up_block,
)
from core.orchestra_agents.backends.sgr.support.settings import (
    SGRRuntimeSettings as SGRRuntimeSettings,
)
from core.orchestra_agents.backends.sgr.support.settings import (
    normalize_int as normalize_int,
)
from core.orchestra_agents.backends.sgr.support.settings import (
    normalize_optional_str as normalize_optional_str,
)
