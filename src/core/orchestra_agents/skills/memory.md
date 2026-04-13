<SKILL_MEMORY>
Store and retrieve persistent memory entries scoped to the current agent.

## Valid room values (MUST use these exact names)
- `profile` — user identity, name, role
- `knowledge` — facts, learned information
- `task` — ongoing tasks, todo items

## Valid category values
- `fact` — factual information
- `preference` — user preferences
- `instruction` — instructions or rules

## When to use memory tools
- User asks "что в памяти" → call `memory_search(query="any", room="knowledge")`
- User says "запомни X" → call `memory_remember` with appropriate room/category
- NEVER answer from chat history — always use `memory_search` first

## Available Tools
- `memory_remember(text, room, category)`: Store a memory entry
- `memory_search(query, room=None, category=None, limit=5)`: Search memories
- `memory_delete(memory_id)`: Delete a memory by ID
- `memory_clear(room=None, category=None)`: Clear memories

## Workflow
1. Question about memory → call `memory_search` with room from valid list
2. Report exact results
3. If no results → "В памяти пока ничего нет"
4. NEVER guess from chat history

## Examples
User: "Что у меня в памяти?"
→ Call: memory_search(query="any", room="knowledge", limit=5)

User: "Запомни что я люблю пиццу"
→ Call: memory_remember(text="user likes pizza", room="knowledge", category="preference")

User: "Какие у меня задачи?"
→ Call: memory_search(query="task", room="task", limit=10)
</SKILL_MEMORY>
