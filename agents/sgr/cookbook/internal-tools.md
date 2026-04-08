# Internal tools

The SGR backend supports three internal tools:

- `reasoning_tool` — stores structured reasoning in session-scoped context memory.
- `final_answer_tool` — records the final answer internally. The LLM should then use an MCP send tool to deliver it.
- `clarification_tool` — records clarification questions internally. The LLM should then use an MCP send tool to ask them.

These tools are local to the runtime and are not routed through external MCP servers.
Internal tool entries are scoped to the current session key for proper isolation.
