"""Runtime entrypoint for the secretary agent.

Secretary uses the standard SGR runtime with MCP servers loaded from manifest.
"""

from __future__ import annotations

from agents.sgr.agent_runtime.main import main as _sgr_main


def main() -> None:
    """Start the secretary agent runtime."""
    _sgr_main()


if __name__ == "__main__":
    main()
