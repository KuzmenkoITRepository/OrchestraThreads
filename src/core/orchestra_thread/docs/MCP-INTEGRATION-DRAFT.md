# OrchestraThreads MCP Integration Draft

## Goal

Подключить `OrchestraThreads` к агентам как MCP так, чтобы:

- `thread_id` оставался durable identity работы;
- маршрутизация и lifecycle thread жили в сервисе;
- у LLM-агента в контекст попадал только минимально необходимый state;
- полная история thread и transport-детали почти никогда не попадали в prompt.

Идея: разделить transport plane, control plane и LLM-facing surface.

## Core Principle

LLM не должен быть клиентом `thread_service` в низкоуровневом смысле.

LLM должен видеть:

- компактный текущий state thread;
- минимальный набор intent-oriented tools;
- короткие результаты tool calls;
- короткий wake-up summary по новым событиям.

LLM не должен регулярно видеть:

- полную историю `thread_events`;
- callback URLs;
- delivery retry state;
- sequence numbers всех событий;
- raw thread rows;
- routing rules в виде текста на каждом шаге.

## High-Level Architecture

Нужны 3 слоя:

1. `OrchestraThreads` service
   - source of truth для threads/events/delivery/inactivity.

2. `orchestra-threads-mcp`
   - MCP server для LLM-агента.
   - Даёт только компактные tools.
   - Скрывает HTTP API и routing details.

3. `thread runtime adapter`
   - локальный агентский процесс или библиотека;
   - принимает `/event` и `/stop` callbacks от `OrchestraThreads`;
   - хранит raw event log вне prompt;
   - строит compact wake-up summary для runtime loop;
   - выставляет active invocation context для MCP tools.

## Separation Of Concerns

`OrchestraThreads`:

- создаёт/reuse root thread;
- создаёт/reuse child thread;
- валидирует ownership/status rules;
- доставляет events;
- генерирует inactivity;
- каскадно закрывает children.

`thread runtime adapter`:

- принимает новые events;
- дедупит и сохраняет raw payload locally;
- обновляет compact thread projection;
- формирует короткий prompt block;
- прокидывает `thread_id`, `root_thread_id`, `parent_thread_id`, `source_agent_slug` в active context.

`orchestra-threads-mcp`:

- читает active context;
- по умолчанию не требует от модели указывать `thread_id`;
- даёт intent-level tools;
- возвращает compact structured responses.

## Why This Minimizes Context

Наибольший расход контекста обычно происходит не на tool call, а на двух местах:

1. при доставке новых событий в prompt;
2. при возврате слишком подробных результатов tools.

Поэтому экономия должна происходить именно там:

- incoming events агрегируются до одного компактного summary;
- tool responses возвращают только минимальный state delta;
- full history остаётся во внешнем store и подтягивается только on-demand.

## LLM-Facing MCP Surface

Для LLM-facing MCP сервера лучше оставить только 5 tools:

1. `thread_send`
2. `thread_status`
3. `thread_current`
4. `thread_expand`
5. `thread_guide`

Все admin/debug tools должны жить в отдельном MCP server или быть скрыты от LLM.

Это важно: длинный список tools сам по себе расходует контекст.

## Tool Design

### 1. `thread_send`

Назначение:

- отправить message в текущий thread;
- открыть/reuse root thread вне активного invocation;
- создать/reuse child thread при делегации третьему агенту.

Аргументы:

- `message`
- `target_agent_slug` optional
- `mode` optional: `auto | root | child | exact`
- `thread_id` optional, только для debug/forced routing

Правило по умолчанию:

- если есть active invocation и `target_agent_slug == source_agent_slug`, это reply в текущий thread;
- если есть active invocation и `target_agent_slug != source_agent_slug`, это child thread;
- если active invocation нет, это root thread.

Для LLM это выглядит как один tool, а не как набор routing решений.

### 2. `thread_status`

Назначение:

- отправить `in_progress | review | done | closed`.

Аргументы:

- `status`
- `message`
- `thread_id` optional

Если `thread_id` не передан, tool берёт его из active context.

### 3. `thread_current`

Назначение:

- вернуть компактный state текущего thread без полной истории.

Возвращает:

- `thread_id`
- `scope`: `root | child`
- `peer_agent_slug`
- `owner_agent_slug`
- `status`
- `waiting_on`
- `last_event_kind`
- `last_message_from`
- `summary`
- `allowed_actions`

### 4. `thread_expand`

Назначение:

- редкий on-demand доступ к деталям.

Аргументы:

- `view`: `latest | tail | related | full`
- `limit` optional
- `thread_id` optional

`thread_expand` должен вызываться только если без деталей реально нельзя продолжать.

### 5. `thread_guide`

Назначение:

- получить каноническую инструкцию по работе с `OrchestraThreads`;
- подтянуть routing/status/tool-flow rules on-demand;
- не держать длинную operational prompt-инструкцию в контексте постоянно.

Аргументы:

- `view`: `compact | full`
- `section` optional: `overview | workflow | routing | statuses | delivery | mcp | mcp_tools`

По умолчанию:

- `compact` возвращает короткий guide с workflow и ключевыми rules;
- `section` позволяет забрать только нужный фрагмент, если модели нужен минимум контекста.

## Compact-By-Default Responses

Все обычные tool responses должны быть короткими.

### Good response shape

```json
{
  "ok": true,
  "thread_id": "5eb72e3e-5469-495e-a3cf-7adb59387b6c",
  "route": "reused_root",
  "status": "open",
  "peer": "orchestra"
}
```

### Bad response shape

```json
{
  "success": true,
  "thread": { "...full thread row..." },
  "event": { "...full event row..." },
  "related": { "...child/root group..." }
}
```

Правило:

- после `send` и `status` возвращать только то, что меняет дальнейшее решение модели;
- не эхо-возвращать весь `message_text`;
- не возвращать историю событий;
- не возвращать delivery metadata.

## Event Ingestion Strategy

Callback `/event` не должен напрямую попадать в prompt как raw JSON.

Вместо этого `thread runtime adapter` делает 4 шага:

1. сохраняет raw events локально;
2. дедупит по `event_id`;
3. обновляет compact thread projection;
4. генерирует один короткий wake-up block.

## Compact Wake-Up Block

Рекомендуемый формат:

```text
=== THREAD UPDATE ===
thread: 5eb72e3e root reply secretary<->orchestra
state: open, waiting_on=orchestra, allowed=send|in_progress|review
new: message from secretary
ask: Prepare a short update for the user.
note: 2 older progress updates were folded.
```

Свойства:

- максимум 5-7 коротких строк;
- только actionable state;
- только последний вопрос/запрос;
- предыдущие notifications можно сворачивать в одну строку;
- raw history не включать.

## Compact Thread Projection

Локально у агента нужно хранить не только raw events, но и derived view:

- `thread_id`
- `root_thread_id`
- `parent_thread_id`
- `peer_agent_slug`
- `owner_agent_slug`
- `status`
- `last_message_from`
- `last_message_preview`
- `last_actionable_summary`
- `waiting_on`
- `allowed_actions`
- `unread_event_count`
- `last_sequence_no`

Именно эта projection должна быть источником для `thread_current`.

## Active Invocation Context

Чтобы не заставлять LLM постоянно писать `thread_id`, MCP server должен читать active context из runtime.

В active context достаточно хранить:

- `thread_id`
- `root_thread_id`
- `parent_thread_id`
- `source_agent_slug`
- `target_agent_slug`
- `owner_agent_slug`
- `current_mode`: `reply | child | root`

Это не prompt context, а machine context.

Именно он даёт главную экономию:

- `thread_status("review", "...")` не требует указывать `thread_id`;
- `thread_send("...", target_agent_slug="specialist")` внутри root thread автоматически становится child routing;
- обычный reply не требует от модели помнить идентификаторы.

## Split MCP Servers

Лучше разделить MCP на два сервера:

1. `orchestra-threads-mcp`
   - только LLM-facing compact tools.

2. `orchestra-threads-admin-mcp`
   - list threads;
   - full thread inspection;
   - raw events;
   - delivery diagnostics;
   - repair/replay/debug.

Причина:

- debug tools редко нужны модели;
- но сами их описания и schema тратят context;
- человеку или оператору они нужны отдельно.

## Service API Extensions Recommended For MCP

Чтобы MCP был действительно compact-by-default, сервису полезно добавить отдельные compact endpoints:

- `GET /api/v1/threads/{thread_id}/compact`
- `GET /api/v1/threads/{thread_id}/tail?limit=3`
- `GET /api/v1/threads/{thread_id}/permissions`

`/compact` должен возвращать derived state, а не full history.

Пример:

```json
{
  "thread_id": "5eb72e3e-5469-495e-a3cf-7adb59387b6c",
  "scope": "root",
  "peer_agent_slug": "orchestra",
  "owner_agent_slug": "secretary",
  "status": "review",
  "waiting_on": "secretary",
  "last_message_from": "orchestra",
  "summary": "orchestra prepared a draft and requests owner review",
  "allowed_actions": ["thread_send", "thread_status:done", "thread_status:closed"]
}
```

## Recommended Runtime Flow

### Outside any active thread

1. агент получает внешний user/system signal;
2. runtime выбирает `thread_send(target_agent_slug="orchestra", ...)`;
3. MCP вызывает сервис;
4. сервис создаёт или reuse root thread;
5. MCP возвращает только compact ack.

### Inside an active thread

1. callback event приходит в adapter;
2. adapter строит compact wake-up block;
3. runtime продолжает reasoning в том же контексте;
4. модель использует `thread_send` или `thread_status`;
5. routing определяется active context, а не текстом в prompt.

## Rules For Minimizing Prompt Growth Over Time

1. Не вставлять full event log в prompt.
2. Не вставлять одинаковые routing rules в каждый wake-up block.
3. Не возвращать full thread object после каждого tool call.
4. Не требовать от модели помнить `thread_id`.
5. Сводить несколько `in_progress` notifications в один folded summary.
6. Доставлять в prompt только последний actionable ask.
7. Детали подтягивать только через explicit `thread_expand`.

## MVP Recommendation

Для ближайшей реализации я бы делал так:

### Step 1

Добавить локальный `orchestra-threads-mcp` с 5 tools:

- `thread_send`
- `thread_status`
- `thread_current`
- `thread_expand`
- `thread_guide`

### Step 2

Добавить `thread runtime adapter`, который:

- принимает callbacks;
- хранит raw events locally;
- строит compact wake-up block;
- выставляет active invocation context.

### Step 3

Добавить в сервис compact projection endpoints.

## Expected Result

При таком подходе модель:

- почти никогда не видит raw thread history;
- почти никогда не указывает `thread_id` руками;
- не тратит контекст на transport-level JSON;
- видит только краткое "что произошло" и "что можно сделать дальше".

Именно это даёт минимальное потребление контекста без потери durable thread semantics.
