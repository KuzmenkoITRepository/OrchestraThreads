<SKILL_ORCHESTRATION>
Manage threads, delegate work to agents, and track execution status.

## Available Tools
- `thread_send`: Send a message or delegate work to another agent
- `thread_status`: Publish thread status (in_progress, review, done, closed)
- `thread_current`: Get compact state of the active thread
- `thread_expand`: Expand thread details (view="latest", "tail", "related", "full")
- `thread_peers`: List available agents and their online status
- `agent_status`: Check if an agent is online/busy without waking it
- `thread_guide`: Fetch the canonical OrchestraThreads workflow rules

## Workflow
1. When the user asks you to coordinate work or talk to another agent
2. Use `thread_send(target_agent_slug=..., message=...)` to delegate
3. Wait for the response by checking `thread_current` or `thread_expand`
4. Report the result back to the user via `send_telegram_message`
5. Close the thread with `thread_status(status="closed")` when done

## Rules
- Use `thread_current` first after context loss to restore state
- Use `thread_expand(view="latest")` to read exact message content
- After delegating, track the response and report back to the user
- Do not leave threads open - close them when work is complete
- Never tell the user "I don't have context" - restore it yourself

## Examples
User: "Ask orchestra what tools it has"
→ Call: thread_send(target_agent_slug="orchestra", message="What tools do you have access to?")
→ Wait for response, check: thread_expand(view="latest")
→ Call: send_telegram_message with the exact response

User: "Is dev agent available?"
→ Call: agent_status(target_agent_slug="dev")
→ Report the online/busy status
</SKILL_ORCHESTRATION>
