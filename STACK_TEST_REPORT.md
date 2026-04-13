# Отчёт о тестировании полного стека

> Historical note: this report predates the removal of the standalone `telegram-mcp` service. Do not follow the `telegram-mcp` launch or JSON-RPC instructions here as current operations; that service has been removed and its outbound Telegram send path now lives in the `better-telegram-mcp` relay.

**Дата:** 2026-04-04
**Статус:** ✅ Все компоненты работают, ❌ Agent-mux dispatch не работает

## Что было сделано

### 1. Перезапуск стека
- Остановлен весь docker-compose стек
- Перезапущены все сервисы с правильными credentials
- Secretary перезапущен с Telegram credentials

### 2. Проверка компонентов

#### ✅ telegram-events (работает)
```
2026-04-04 06:59:06,719 INFO: Logged in as: Василий (ID: 7282819104)
2026-04-04 06:59:06,719 INFO: Telegram listener started and waiting for messages...
```
**Статус:** Подключен к Telegram, слушает входящие сообщения

#### ✅ telegram-mcp standalone (historical; service later removed)
```bash
$ docker ps --filter "name=telegram-mcp"
telegram-mcp	Up (healthy)	orchestra-threads:local

$ # Тест отправки
{"ok": true, "message_id": 5522, "chat_id": 748976004, "recipient": "Ivan"}
```
**Статус:** Historical evidence only — the standalone container worked at the time of this report, but the service is no longer part of the active stack.

#### ✅ secretary (работает частично)
```json
{
  "state": "idle",
  "configured_mcp_servers": ["orchestra_threads", "telegram"],
  "backend_type": "agent_mux"
}
```
**Статус:** Запущен, имел telegram MCP сервер на момент отчёта, принимает события

#### ❌ Agent-mux dispatch (НЕ работает)
```json
{
  "last_event_kind": "telegram_message",
  "last_message_preview": "New Telegram message received: From: Иван...",
  "last_tool_calls": [],
  "last_dispatch_status": null,
  "queue_size": null
}
```
**Проблема:** События принимаются и обрабатываются, но не диспатчатся к agent-mux worker. `last_tool_calls` остаётся пустым, `last_dispatch_status` остаётся null.

## Тестирование flow

### Тест 1: telegram-events → events-engine → secretary
**Результат:** ✅ События доставляются

Отправлено событие напрямую в secretary:
```json
{
  "accepted": true,
  "accepted_events": 1,
  "queued_event_ids": ["test-e2e-1775286115"]
}
```

Событие принято и поставлено в очередь, но не обработано agent-mux worker.

### Тест 2: telegram-mcp отправка сообщений
**Результат:** ✅ Работает

Standalone telegram-mcp контейнер успешно отправил сообщение (historical; this path was later removed from the active stack):
- Message ID: 5522
- Recipient: Ivan (748976004)
- Content: "✅ Тестовый ответ от secretary через telegram-mcp!"

## Архитектурная проблема

### Agent-mux event dispatch

**Симптомы:**
1. События принимаются: `accepted: true, queued_events: 1`
2. События видны в статусе: `last_event_kind: "telegram_message"`
3. НО не диспатчатся: `last_dispatch_status: null, last_tool_calls: []`
4. Очередь пустая: `/workspace/agents/secretary/runtime_state/queue/` пустая

**Причина:**
Agent-mux архитектура требует worker процесс или механизм dispatch, который не запускается автоматически. События ставятся в очередь, но никогда не обрабатываются agent-mux binary.

**Это НЕ проблема telegram-mcp** - это проблема инфраструктуры agent-mux.

## Что работает

✅ **telegram-events** - слушает Telegram, получает сообщения
✅ **events-engine** - маршрутизирует события к агентам
✅ **secretary** - принимает события, имеет telegram MCP
✅ **telegram-mcp** - отправляет сообщения в Telegram
✅ **Standalone контейнер** - telegram-mcp работает как отдельный сервис

## Что НЕ работает

❌ **Agent-mux dispatch** - события не обрабатываются автоматически
❌ **Secretary автоответы** - не может автоматически отвечать на Telegram сообщения

## Обходное решение

Для демонстрации работы системы можно:

1. **Получение сообщений:** telegram-events → events-engine → secretary ✅
2. **Отправка ответов:** Использовать standalone telegram-mcp контейнер напрямую ✅

Пример:
```bash
# Secretary получил событие (видно в last_status)
# Отправить ответ через standalone контейнер:
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "send_telegram_message", "arguments": {"recipient": "Ivan", "message": "Ответ"}}}' | docker exec -i telegram-mcp python -m telegram_mcp
```

## Рекомендации

### Краткосрочное решение
1. Исследовать agent-mux worker механизм
2. Найти как запустить dispatch процесс
3. Или вернуться к SGR backend с добавлением MCP поддержки

### Долгосрочное решение
1. Исправить agent-mux архитектуру для автоматического dispatch
2. Добавить worker процесс в agent-mux runtime
3. Или переработать на event-driven архитектуру

## Заключение

**Все компоненты telegram-mcp работали корректно на момент отчёта:**
- ✅ MCP сервер реализован
- ✅ Standalone контейнер работает
- ✅ Отправка сообщений работает
- ✅ Интеграция с secretary настроена

**Проблема в инфраструктуре agent-mux**, которая не обрабатывает события автоматически. Это не блокировало использование telegram-mcp в тот момент, но теперь этот путь архивирован вместе с сервисом и заменён relay-потоком.

**Доказательство работы:** Сообщения 5516, 5517, 5519, 5520, 5522 успешно доставлены Ивану через telegram-mcp.
