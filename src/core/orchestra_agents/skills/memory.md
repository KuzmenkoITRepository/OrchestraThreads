<SKILL_MEMORY>
Store and retrieve persistent memory entries scoped to the current agent.

## Available Tools
- `memory_remember`: Store a memory entry (requires: text, room, category)
- `memory_search`: Search memory entries (requires: query, optional: room, category, limit)
- `memory_delete`: Delete a memory entry by ID (requires: memory_id)
- `memory_clear`: Clear memory entries (optional: room, category filters)

## Workflow
1. When the user asks you to remember something or check what's in memory
2. Use `memory_remember` to store new information with appropriate room/category
3. Use `memory_search` to find existing memories by query
4. Use `memory_delete` to remove specific entries
5. Use `memory_clear` to reset memory (with optional filters)

## Rules
- Always scope memories to the appropriate room and category
- Use descriptive text that captures the key information
- When searching, use relevant keywords from the query
- Do not store sensitive information (passwords, tokens, secrets)
- Memory entries are agent-scoped - each agent has its own memory space

## Examples
User: "Remember that the API key is xyz123"
→ Call: memory_remember(text="API key is xyz123", room="config", category="credentials")

User: "What do you remember about the project?"
→ Call: memory_search(query="project", limit=5)

User: "Clear my config memory"
→ Call: memory_clear(room="config")
</SKILL_MEMORY>
