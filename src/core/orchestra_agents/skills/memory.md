<SKILL_MEMORY>
Store and retrieve persistent memory entries scoped to the current agent.

## Room and Category Values

**Discovery-first approach**: Always call `memory_list_rooms()` and `memory_list_categories()` to see what values exist for the current agent.

**Common room values** (examples, not exhaustive):
- `profile` — user identity, name, role
- `knowledge` — facts, learned information
- `task` — ongoing tasks, todo items
- `context` — session context, conversation history

**Common category values** (examples, not exhaustive):
- `fact` — factual information
- `preference` — user preferences
- `instruction` — instructions or rules
- `decision` — architectural or design decisions

You can create new rooms and categories as needed using `memory_remember(text, room="your_room", category="your_category")`.
## When to use memory tools
- User asks "что в памяти" → call `memory_search(query="any", room="knowledge")`
- User says "запомни X" → call `memory_remember` with appropriate room/category
- NEVER answer from chat history — always use `memory_search` first

## Available Tools
- `memory_remember(text, room, category)`: Store a memory entry
- `memory_search(query, room=None, category=None, limit=5)`: Search memories
- `memory_list_rooms()`: List available room names for this agent
- `memory_list_categories()`: List available category names for this agent
- `memory_delete(memory_id)`: Delete a memory by ID
- `memory_clear(room=None, category=None)`: Clear memories

## Workflow
1. **Discover available values**: Call `memory_list_rooms()` and `memory_list_categories()` to see what exists for the current agent
2. **Search before storing**: Before using `memory_remember`, call `memory_search` with room from valid list to avoid duplicates
3. **Store with appropriate room/category**: Use discovered values or create new descriptive ones
4. **Report exact results**: Never guess from chat history
5. **If no results**: Report "В памяти пока ничего нет"
6. **Create new rooms/categories as needed**: If stored values don't exist, they will be created automatically

## Examples
User: "Что у меня в памяти?"
→ Call: memory_search(query="any", room="knowledge", limit=5)

User: "Запомни что я люблю пиццу"
→ Call: memory_remember(text="user likes pizza", room="knowledge", category="preference")

User: "Какие у меня задачи?"
→ Call: memory_search(query="task", room="task", limit=10)
</SKILL_MEMORY>
