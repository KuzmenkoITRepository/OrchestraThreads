<SKILL_MEMORY>
Store and retrieve persistent memory entries scoped to the current agent.

## When to use memory tools
- User asks "что в памяти", "что ты помнишь", "что сохранено" → ALWAYS call `memory_search`
- User says "запомни X" → ALWAYS call `memory_remember` with appropriate room/category
- NEVER answer memory questions from chat history alone — always use `memory_search`

## Available Tools
- `memory_remember`: Store a memory entry (required: text, room, category)
- `memory_search`: Search memory entries (required: query, optional: room, category, limit)
- `memory_delete`: Delete a memory entry by ID (required: memory_id)
- `memory_clear`: Clear memory entries (optional: room, category filters)

## Valid room values
Use these exact room names — DO NOT invent new ones:
- `preferences` — user preferences, likes, dislikes
- `context` — working context, ongoing tasks
- `credentials` — API keys, tokens (use cautiously)
- `notes` — general notes and observations
- `facts` — facts about user or project

## Workflow
1. When question is about memory → call `memory_search` with relevant keywords
2. Use `room` parameter to filter by area, or omit to search all
3. Report the exact results from memory_search response
4. If no results found → say so honestly: "В памяти пока ничего нет"
5. NEVER guess from chat history — always query memory first

## Rules
- Use the valid room names listed above
- Use descriptive text that captures key information
- When searching, use broad keywords to find relevant entries
- Do NOT store sensitive information (passwords, tokens, secrets)

## Examples
User: "Что у меня в памяти?"
→ Call: memory_search(query="all", limit=10)
→ Report results exactly as returned

User: "Запомни что я люблю пиццу"
→ Call: memory_remember(text="user likes pizza", room="preferences", category="personal")

User: "Что ты помнишь о проекте?"
→ Call: memory_search(query="project", room="context", limit=5)
→ Report results
</SKILL_MEMORY>
