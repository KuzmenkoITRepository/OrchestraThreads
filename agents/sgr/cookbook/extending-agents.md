# Extending specialized agents

To build a specialized agent on top of this backend:

1. Create a new manifest using the SGR runtime entrypoint.
2. Provide a task-specific `system_prompt.md`.
3. Reuse the built-in internal tools and thread MCP tools.
4. Keep the prompt compact and rely on context memory plus compact thread state.

This backend is intended to be extended by prompts and manifest configuration, not by duplicating runtime logic.
