<SKILL_MEMORY>
Store and retrieve persistent memory entries scoped to the current agent.

## When to use memory tools
- User asks "что в памяти", "что ты помнишь", "что сохранено" → ALWAYS call `memory_search` first
- User says "запомни X" → ALWAYS call `memory_remember` with appropriate room/category
- After /clear or context reset → call `memory_search(query="recent")` to restore working context
- NEVER answer memory questions from chat history alone — always use `memory_search`

## Available Tools
- `memory_remember`: Store a memory entry (required: text, room, category)
- `memory_search`: Search memory entries (required: query, optional: room, category, limit)
- `memory_delete`: Delete a memory entry by ID (required: memory_id)
- `memory_clear`: Clear memory entries (optional: room, category filters)

## Workflow
1. When question is about memory → call `memory_search` with relevant keywords
2. Report the exact results from memory_search response
3. If no results found → say so honestly: "В памяти пока ничего нет"
4. NEVER guess from chat history — always query memory first

## Rules
- Always scope memories to appropriate room and category
- Use descriptive text that captures key information
- When searching, use relevant keywords from the query
- Do NOT store sensitive information (passwords, tokens, secrets)
- Memory entries are agent-scoped — each agent has its own memory space

## Examples
User: "Что у меня в памяти?"
→ Step 1: Call memory_search(query="any", limit=10)
→ Step 2: Report results exactly as returned

User: "Запомни что я люблю пиццу"
→ Call: memory_remember(text="User likes pizza", room="preferences", category="personal")

User: "/clear" then "Что ты помнишь?"
→ Step 1: Call memory_search(query="recent", limit=5)
→ Step 2: Report what memory contains
</SKILL_MEMORY>
