# TELEGRAM BOT LISTENER DOMAIN

## OVERVIEW
`telegram_bot_listener` = standalone Telegram Bot API polling service. Owns long-poll intake, local state tracking, update processing, outbound event forwarding, small HTTP control surface.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Runtime entry | `service_main.py` | signal handling + long-lived boot |
| Core runtime | `service_runtime.py` | `TelegramBotListenerConfig`, `TelegramBotListenerService` |
| App/config helpers | `service_app.py`, `service_config.py` | app build + service construction |
| Facade export | `service.py` | thin re-export, not main logic |
| Telegram API + forwarding | `bot_api.py`, `event_forwarder.py` | upstream bot calls + events-engine delivery |
| Update pipeline | `update_processor.py`, `update_processor_runtime.py`, `update_polling.py`, `update_message_processing.py`, `update_callback_processing.py`, `update_state_interactions.py`, `update_filters.py` | inbound update flow |
| Local state | `state_store.py`, `state_store_parts/` | persisted polling/update state |
| HTTP surface | `http_handlers.py`, `http_payloads.py`, `http_send_ops.py` | control/send endpoints |
| Tests | `tests/` | service integration coverage |

## CONVENTIONS
- Keep polling, update parsing, state mutation, outbound forwarding as separate steps.
- Service health meaning is tied to polling task being alive.
- Preserve split between service construction (`service_config.py`) and runtime execution (`service_runtime.py` / `service_main.py`).

## ANTI-PATTERNS
- Do not bury Telegram API calls inside generic HTTP handlers.
- Do not bypass state-store helpers when changing update progression semantics.
- Do not let this service absorb thread or registry ownership. It is polling/forwarding edge only.

## COMMANDS
```bash
PYTHONPATH=src python -m core.telegram_bot_listener.service_main
docker compose --profile test run --rm test
```

## NOTES
- `tests/test_service_integration.py` = first behavior check after polling/forwarding changes.
