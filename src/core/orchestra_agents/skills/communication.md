<SKILL_COMMUNICATION>
Send messages to users via Telegram or other communication channels.

## Available Tools
- `send_telegram_message`: Send a message to Ivan via Telegram

## Workflow
1. When the user asks you to send a message or reply to someone
2. Use `send_telegram_message` with the appropriate recipient and message text
3. Keep messages concise and action-oriented
4. Do not mention internal details (thread IDs, agent slugs, etc.)

## Rules
- Always use `send_telegram_message` for user-facing communication
- When the recipient is Ivan, use `recipient: "ivan"`
- Keep messages structured and actionable
- Do not send raw technical details to users
- If the user asks for an agent's response, quote the exact response text

## Examples
User: "Tell Ivan the job is done"
→ Call: send_telegram_message(recipient="ivan", message="Job is done")

User: "What did orchestra say?"
→ First call: thread_expand(view="latest") to get the exact response
→ Then call: send_telegram_message with the quoted response
</SKILL_COMMUNICATION>
