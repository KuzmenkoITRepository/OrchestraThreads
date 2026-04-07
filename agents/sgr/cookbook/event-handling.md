# Event handling

The runtime processes all actionable events in a delivery batch.

Supported actionable events:

- response-required `message`
- `inactive` when `react_to_inactive=true`
- `notification` with a non-empty `notification_status`

If no outward action is emitted, the runtime returns a graceful success result with `reason=no_tool_action_emitted` instead of crashing.
