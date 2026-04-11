"""Compatibility facade for the manual agent CLI package."""

from core.orchestra_thread.agent_cli.app import (
    ManualAgentCLI as ManualAgentCLI,
)
from core.orchestra_thread.agent_cli.app import (
    _build_arg_parser as _build_arg_parser,
)
from core.orchestra_thread.agent_cli.app import (
    main as main,
)
