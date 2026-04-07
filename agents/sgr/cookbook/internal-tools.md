# Internal tools

The SGR backend supports three internal tools:

- `reasoning_tool` — stores structured reasoning in in-memory context.
- `final_answer_tool` — sends the final answer through `thread_send`.
- `clarification_tool` — sends clarification questions through `thread_send`.

These tools are local to the runtime and are not routed through external MCP schemas.
