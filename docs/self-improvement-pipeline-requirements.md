# Self-Improvement Pipeline — Requirements

**Status:** draft
**Date:** 2026-04-11
**Depends on:** ORCHESTRA-AGENTS.md (arch spec), deploy/ (existing infra)

---

## 1. Unified Goal

Агентский ансамбль OrchestraAgents должен уметь **автономно улучшать себя** —
находить проблемы, разрабатывать исправления и новый функционал, тестировать
изменения в изолированном окружении и доставлять их на прод — без ручного
вмешательства owner, но с возможностью owner заблокировать или откатить
любое изменение в любой момент.

### 1.1 Что значит "уметь улучшать себя"

Ансамбль должен поддерживать полный замкнутый цикл:

```
обнаружение проблемы / идеи
  → декомпозиция и постановка задачи
  → разработка в изолированном окружении
  → автоматическое тестирование (unit + e2e acceptance)
  → review и approval
  → доставка на prod
  → верификация на prod
  → откат, если что-то пошло не так
  → cleanup staging-окружения
```

Каждый шаг выполняется конкретным агентом через конкретные инструменты.
Orchestra координирует, но не выполняет работу сам.

### 1.2 Критические свойства цикла

| Свойство | Требование |
|----------|-----------|
| Изоляция | Ни один шаг разработки/тестирования не затрагивает prod |
| Наблюдаемость | Каждый шаг оставляет trace в thread-коммуникациях |
| Обратимость | Любое изменение на prod можно откатить к предыдущему known-good состоянию |
| Устойчивость к сбоям | Падение на любом шаге не ломает prod и не оставляет мусор |
| Approval gate | Prod-деплой невозможен без подтверждений от orchestra и qa |
| Owner override | Owner может заморозить / отменить / откатить любое изменение |

### 1.3 Чего ансамбль НЕ делает автономно

- Не меняет собственную governance-модель (роли, доступы, approval chain)
- Не создаёт новых агентов без подтверждения owner
- Не удаляет prod-данные
- Не меняет Vault-секреты prod без подтверждения owner
- Не отключает мониторинг и healthcheck

---

## 2. Источники изменений

Изменения в систему попадают из трёх каналов:

### 2.1 Запрос от owner

Owner через main-secretary → orchestra → task → dev.
Высший приоритет. Может обходить очередь.

### 2.2 Внутреннее обнаружение (whiner, qa, devops)

- **whiner** обнаруживает проблему через анализ логов / опрос агентов
- **qa** обнаруживает регрессию через плановый прогон тестов
- **devops** обнаруживает деградацию через мониторинг healthcheck

Канал: thread к orchestra → orchestra оценивает и приоритизирует → task → dev.

### 2.3 Плановые улучшения (scheduler → orchestra)

Scheduler будит orchestra по расписанию. Orchestra проверяет:
- есть ли задачи в backlog
- есть ли результаты от whiner
- есть ли проваленные тесты от qa

Если есть работа — запускает цикл.

---

## 3. Изолированные окружения

### 3.1 Существующая инфраструктура

Проект уже имеет полный набор для создания изолированных окружений:

- `provision-environment.sh` — создаёт окружение с нуля
- `deploy-env.sh` — деплоит стек в окружение
- `teardown-environment.sh` — удаляет окружение полностью
- `worktree-manager.sh` — git worktree для изоляции кода
- `port-allocator.sh` — уникальные порты для каждого окружения
- `create-env.sh` — Vault secret path + AppRole per env

### 3.2 Требования к staging-окружению

Staging-окружение — это полная копия prod-стека, работающая параллельно
с prod на той же машине, но полностью изолированная.

#### Что должно быть изолировано

| Ресурс | Изоляция | Механизм |
|--------|---------|----------|
| Код | Отдельный git worktree | `worktree-manager.sh` |
| Docker | Отдельный compose project | `COMPOSE_PROJECT_NAME=orchestrathreads-stg-<id>` |
| Postgres | Отдельный контейнер + volume | Отдельный `postgres` сервис в compose |
| Порты | Уникальные, не пересекаются с prod | `port-allocator.sh` |
| Vault secrets | Отдельный path | `kv/orchestrathreads/stg-<id>/runtime` |
| OmniRoute | Отдельный инстанс | Свой порт, своя data-dir |
| Telegram | Test-аккаунт или mock | Отдельные `TELEGRAM_API_ID` / `TELEGRAM_SESSION_STRING` |
| Agent runtime state | Отдельные `runtime_state/` dirs | В worktree workspace |
| Docker network | Отдельная bridge-сеть | Автоматически через отдельный compose project |

#### Telegram-изоляция — критический момент

Prod использует реальный Telegram-аккаунт. Staging **не может** использовать
тот же аккаунт — это вызовет конфликт сессий (документировано в
`docs/tasks/003-telegram-session-conflict-kills-listener.md`).

Варианты для staging:

1. **Отдельный Telegram test-аккаунт** — полная e2e проверка, но требует
   второй номер телефона и ручную авторизацию Telethon-сессии.
2. **Mock telegram-events** — HTTP-заглушка, отдающая фиксированные ответы.
   Достаточно для acceptance-тестов, не требует внешних зависимостей.
3. **Гибрид** — mock по умолчанию, test-аккаунт для полных прогонов.

**Рекомендация:** начать с варианта 2 (mock), добавить вариант 1 позже.

#### Именование staging-окружений

Формат: `stg-<short-purpose>` (например `stg-fix-thread-retry`, `stg-add-memory-tool`).
Максимальная длина: 32 символа (ограничение `validate_env_name`).

#### Lifecycle staging-окружения

```
provision → develop → test → [approve] → teardown
                ↑         |
                └─────────┘  (если тесты не прошли — доработка)
```

Staging живёт до тех пор, пока:
- Изменение не доставлено на prod и не верифицировано, или
- Orchestra явно не отменил задачу

**Требование:** максимальный возраст staging — 72 часа. Если staging
старше — whiner поднимает вопрос, orchestra принимает решение (продлить
или teardown).

### 3.3 Требования к prod-окружению

Prod всегда работает на конкретном зафиксированном ref (git commit).
Деплой на prod возможен **только** при наличии:

- `deploy/approvals/<ref>.approved-by-orchestra`
- `deploy/approvals/<ref>.approved-by-qa`

Это уже реализовано в `_require_prod_approvals()` внутри `deploy-env.sh`.

---

## 4. Pipeline MCP Server

### 4.1 Назначение

Агенты не вызывают bash-скрипты напрямую. Им нужен MCP-сервер, который
предоставляет высокоуровневые инструменты для работы с pipeline.

Pipeline MCP — тонкая обёртка над существующими `deploy/` скриптами,
которая добавляет:
- Проверку прав вызывающего агента
- Structured JSON ответы
- Логирование в thread (чтобы orchestra видел прогресс)
- Idempotency (повторный вызов не ломает состояние)

### 4.2 Инструменты

#### `pipeline_provision_staging`

**Кто вызывает:** dev (через orchestra)
**Что делает:** создаёт изолированное staging-окружение для ветки/задачи.
**Входные параметры:**
- `name` — имя окружения (slug, ≤32 символа)
- `base_env` — на основе какого окружения создавать (default: `dev`)
- `deploy_ref` — git ref для worktree (default: текущий HEAD ветки)

**Что происходит внутри:**
1. Валидация имени и проверка что окружение не существует
2. Вызов `provision-environment.sh <name> <base_env>`
3. Ожидание healthcheck всех сервисов
4. Возврат structured result: имя, порты, workspace path, статус сервисов

**Ответ при ошибке:** детальное описание, на каком шаге упало и что в логах.

#### `pipeline_run_checks`

**Кто вызывает:** dev
**Что делает:** запускает `make check` (format + lint + typecheck) в worktree staging.
**Входные параметры:**
- `environment` — имя staging-окружения

**Ответ:** pass/fail + вывод первых N строк ошибок, если fail.

#### `pipeline_run_unit_tests`

**Кто вызывает:** qa
**Что делает:** запускает `docker compose --profile test run --rm test` в staging.
**Входные параметры:**
- `environment` — имя staging-окружения
- `test_filter` — опциональный фильтр конкретных тест-модулей

**Ответ:** pass/fail + количество passed/failed/errors + output failed тестов.

#### `pipeline_run_acceptance`

**Кто вызывает:** qa
**Что делает:** запускает e2e acceptance test suite против работающего staging-стека.
**Входные параметры:**
- `environment` — имя staging-окружения
- `scenarios` — опциональный список конкретных сценариев (default: все)

**Ответ:** per-scenario pass/fail + timing + details при failure.
Подробнее о acceptance-тестах — раздел 5.

#### `pipeline_get_status`

**Кто вызывает:** все агенты
**Что делает:** возвращает состояние окружения.
**Входные параметры:**
- `environment` — имя окружения (staging или prod)

**Ответ:**
- Статус каждого сервиса (running/healthy/unhealthy/stopped)
- Текущий deployed ref
- Последние результаты тестов (если были)
- Возраст окружения

#### `pipeline_approve`

**Кто вызывает:** orchestra, qa
**Что делает:** создаёт approval-файл для git ref.
**Входные параметры:**
- `ref` — git commit hash
- `role` — `orchestra` или `qa`

**Что происходит внутри:**
1. Проверка что вызывающий агент имеет право создавать approval для этой роли
2. Проверка что ref существует в git
3. Создание файла `deploy/approvals/<ref>.approved-by-<role>`
4. Git commit + push approval-файла

**Защита:** dev и devops не могут вызывать этот инструмент.

#### `pipeline_deploy_prod`

**Кто вызывает:** devops
**Что делает:** деплоит одобренный ref на prod.
**Входные параметры:**
- `ref` — git commit hash

**Что происходит внутри:**
1. Проверка наличия обоих approval-файлов (orchestra + qa)
2. `OT_DEPLOY_REF=<ref> bash deploy/deploy-env.sh prod`
3. Ожидание healthcheck всех сервисов
4. Возврат результата

**Защита:** если нет обоих approval — отказ. Если healthcheck не проходит
в течение таймаута — автоматический откат на предыдущий ref.

#### `pipeline_rollback_prod`

**Кто вызывает:** devops (по решению orchestra или qa)
**Что делает:** откатывает prod на предыдущий known-good ref.
**Входные параметры:**
- `target_ref` — опционально; если не указан — предыдущий deployed ref

**Что происходит внутри:**
1. Определение target ref (предыдущий approved и deployed)
2. Обновление worktree на target ref
3. Перезапуск стека
4. Healthcheck
5. Если healthcheck не проходит — **стек остаётся остановленным**,
   уведомление orchestra → main-secretary → owner

#### `pipeline_teardown_staging`

**Кто вызывает:** devops (по решению orchestra)
**Что делает:** полностью удаляет staging-окружение.
**Входные параметры:**
- `environment` — имя staging-окружения

**Защита:** нельзя teardown prod/dev через этот инструмент.

#### `pipeline_list_environments`

**Кто вызывает:** все агенты
**Что делает:** список активных окружений.
**Ответ:** имя, тип (staging/prod/dev), возраст, текущий ref, статус.

### 4.3 Матрица доступа

| Инструмент | orchestra | dev | qa | devops |
|-----------|-----------|-----|-----|--------|
| provision_staging | — | да | — | да |
| run_checks | — | да | да | — |
| run_unit_tests | — | — | да | — |
| run_acceptance | — | — | да | — |
| get_status | да | да | да | да |
| approve | да | — | да | — |
| deploy_prod | — | — | — | да |
| rollback_prod | — | — | — | да |
| teardown_staging | — | — | — | да |
| list_environments | да | да | да | да |

### 4.4 Технические требования к Pipeline MCP

- Реализуется как Python MCP-сервер аналогично `src/telegram_mcp/`
- Подключается к агентам через manifest.yaml `mcp_servers`
- Каждый инструмент — sync-вызов с таймаутом
- Длительные операции (provision, deploy) возвращают промежуточные статусы
- Все ошибки — structured JSON, не raw stderr
- Логирование каждого вызова с agent_slug, timestamp, params, result

---

## 5. E2E Acceptance Tests

### 5.1 Назначение

Acceptance-тесты отвечают на вопрос:
**"Работает ли система как целое?"**

В отличие от unit/integration тестов (которые проверяют модули изолированно),
acceptance-тесты работают с полностью поднятым стеком и проверяют
сквозные сценарии.

### 5.2 Prerequisite

Acceptance-тесты запускаются **только** на уже поднятом и healthy стеке.
Они не поднимают стек сами — это ответственность provision/deploy.

### 5.3 Сценарии

Каждый сценарий — независимый, может запускаться отдельно.

#### Scenario 1: Thread lifecycle

**Проверяет:** core thread flow — создание, отправка, получение, завершение.

1. Создать thread через HTTP API orchestra-threads
2. Отправить сообщение в thread (имитация агента)
3. Прочитать thread — убедиться, что сообщение доставлено
4. Установить статус `done`
5. Прочитать thread — убедиться, что статус обновился

**Pass criteria:** все шаги завершились без ошибок, данные консистентны.

#### Scenario 2: Agent lifecycle

**Проверяет:** agent start → healthcheck → event delivery → response.

1. Проверить что orchestra-agents service healthy
2. Получить список зарегистрированных агентов
3. Проверить что ожидаемые агенты (orchestra, dev, qa, devops) present
4. Отправить тестовый event в events-engine
5. Проверить что event доставлен целевому агенту (через status или log)

**Pass criteria:** агент получил event, ответил, статус обновился.

#### Scenario 3: Task registry

**Проверяет:** создание задачи, чтение, обновление статуса.

1. Создать задачу через task-registry HTTP API
2. Прочитать задачу — убедиться что создана корректно
3. Обновить статус задачи
4. Прочитать — убедиться что статус обновился

**Pass criteria:** CRUD операции работают, данные консистентны.

#### Scenario 4: Scheduler execution

**Проверяет:** scheduler может создать и выполнить cron-задачу.

1. Создать тестовую cron-задачу через scheduler HTTP API
2. Дождаться выполнения (или trigger вручную)
3. Проверить что задача выполнилась
4. Удалить тестовую задачу

**Pass criteria:** задача выполнена, артефакт/лог присутствует.

#### Scenario 5: Memory service

**Проверяет:** orchestra-memory хранит и отдаёт данные.

1. Записать тестовый memory entry
2. Прочитать / поискать — убедиться что найден
3. Удалить тестовый entry
4. Поискать — убедиться что удалён

**Pass criteria:** write → read → delete → confirm deleted.

#### Scenario 6: MCP server connectivity

**Проверяет:** MCP-серверы (thread, memory, telegram) отвечают.

1. Для каждого MCP-сервера: инициализировать MCP-сессию
2. Получить список доступных tools
3. Убедиться что ожидаемые tools присутствуют

**Pass criteria:** все MCP-серверы отвечают, tools доступны.

#### Scenario 7: Full pipeline (smoke)

**Проверяет:** минимальный happy-path от события до ответа.

1. Отправить сообщение в thread (имитация входящего запроса)
2. Проверить что orchestra получил сообщение
3. Проверить что orchestra может отправить thread_send
4. Проверить что получатель видит ответ

**Pass criteria:** сообщение прошло полный цикл.

#### Scenario 8: Healthcheck sweep

**Проверяет:** все сервисы стека отвечают на healthcheck.

1. Для каждого сервиса из списка: GET `/healthz`
2. Все должны вернуть 200

**Pass criteria:** 100% сервисов healthy.

### 5.4 Технические требования

- Тесты — Python-модуль `src/core/acceptance/`
- Каждый сценарий — отдельный файл/класс
- Таймаут на сценарий: настраиваемый, default 60 секунд
- Результат — structured JSON: scenario name, pass/fail, duration, details
- Тесты не модифицируют persistent state — создают тестовые данные,
  затем зачищают за собой
- Тесты должны быть idempotent: повторный запуск не ломается из-за
  артефактов предыдущего запуска
- Тесты должны работать с любым окружением (staging или prod),
  получая URL сервисов через env vars

### 5.5 Acceptance vs Smoke

| | Acceptance (staging) | Smoke (prod) |
|--|---------------------|-------------|
| Когда | После dev готов, перед approval | После prod-деплоя |
| Scope | Все сценарии | Только scenarios 7 + 8 (pipeline smoke + healthcheck) |
| Действия | Создают тестовые данные | Только read + healthcheck |
| При failure | Возврат на доработку dev | Rollback prod |

---

## 6. Rollback и Recovery

### 6.1 Уровни отката

#### Level 1: Staging fix

Тесты не прошли на staging → dev дорабатывает код, qa перепроверяет.
Prod не затронут. Staging продолжает работать.

#### Level 2: Prod rollback

Smoke на prod не прошёл после деплоя → devops откатывает на предыдущий ref.

Sequence:
1. qa: "smoke failed" → thread к orchestra
2. orchestra: решение "rollback" → thread к devops
3. devops: `pipeline_rollback_prod` → откат
4. qa: повторный smoke → подтверждение восстановления
5. orchestra: создаёт задачу dev на исправление проблемы

#### Level 3: Critical — prod не восстанавливается

Откат не помог (предыдущий ref тоже broken или rollback failed).

Sequence:
1. devops: "rollback failed" → thread к orchestra
2. orchestra: escalation → thread к main-secretary
3. main-secretary: уведомление owner через Telegram
4. orchestra: freeze на все изменения до ручного вмешательства

### 6.2 Механизм отслеживания known-good state

Система должна хранить историю успешных деплоев:

```
deploy/history/
  prod-deploys.log   # timestamp | ref | status (success/rolled-back)
```

Формат строки:
```
2026-04-11T14:30:00Z a58ffa3 success
2026-04-11T15:00:00Z b7ed871 rolled-back
2026-04-10T10:00:00Z 0df818b success
```

`pipeline_rollback_prod` без явного `target_ref` откатывает на последний
ref со статусом `success`.

### 6.3 Автоматический rollback

Помимо ручного rollback (через агентов), должен существовать автоматический:

**Trigger:** если в течение 5 минут после prod-деплоя healthcheck
хотя бы одного core-сервиса (orchestra-threads, orchestra-agents,
events-engine) переходит в unhealthy и не восстанавливается за 2 минуты.

**Action:** автоматический откат на предыдущий known-good ref,
уведомление orchestra.

Это реализуется как часть `deploy-env.sh` — post-deploy health watch
с таймаутом.

---

## 7. Agent Playbooks

### 7.1 Назначение

Playbooks — это конкретные процедуры, которые каждый агент выполняет
на каждом шаге pipeline. Playbooks описываются в system_prompt агентов
и в документации, доступной через MCP-инструменты.

### 7.2 Playbook: Standard improvement cycle

```
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 0: TRIGGER                          │
│  whiner/qa/scheduler/owner → orchestra                      │
│  "есть проблема / идея / задача"                            │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 1: PLAN                             │
│  orchestra:                                                 │
│    1. Оценить scope и приоритет                             │
│    2. Декомпозировать на конкретные шаги                    │
│    3. Создать задачу в task registry                        │
│    4. thread_send dev: "задача + acceptance criteria"       │
│    5. thread_status: in_progress                            │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 2: DEVELOP                          │
│  dev:                                                       │
│    1. pipeline_provision_staging (имя по задаче)            │
│    2. Писать код в worktree staging'а                       │
│    3. pipeline_run_checks → lint/type clean                 │
│    4. git commit в staging worktree                         │
│    5. thread_send orchestra: "ready for QA, ref=<hash>"     │
│    6. thread_status: review                                 │
│                                                             │
│  При ошибке на шаге 3:                                     │
│    → исправить код, повторить с шага 3                      │
│  При невозможности реализовать:                             │
│    → thread_send orchestra с объяснением                    │
│    → orchestra принимает решение                            │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 3: TEST                             │
│  orchestra → qa: "проверь staging <name>, ref <hash>"       │
│                                                             │
│  qa:                                                        │
│    1. pipeline_run_unit_tests (staging)                     │
│    2. pipeline_run_acceptance (staging)                     │
│    3. Ручной анализ результатов                             │
│                                                             │
│  Если ВСЁ зелёное:                                         │
│    → qa: pipeline_approve (ref, role=qa)                    │
│    → qa: thread_send orchestra "approved, all tests pass"   │
│                                                             │
│  Если FAIL:                                                 │
│    → qa: thread_send dev "test failures: <details>"         │
│    → qa: thread_send orchestra "QA blocked: <summary>"      │
│    → НАЗАД К ФАЗЕ 2 (dev дорабатывает)                     │
│                                                             │
│  Max iterations перед эскалацией: 3                         │
│  После 3 провалов → orchestra решает: отменить или         │
│  переформулировать задачу                                   │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 4: APPROVE                          │
│  orchestra:                                                 │
│    1. Проверить что qa approved                             │
│    2. pipeline_approve (ref, role=orchestra)                │
│    3. thread_send devops "deploy ref=<hash> to prod"       │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 5: DEPLOY                           │
│  devops:                                                    │
│    1. pipeline_deploy_prod (ref)                            │
│    2. Проверить результат (healthcheck pass)                │
│    3. thread_send qa "prod deployed, run smoke"             │
│    4. thread_send orchestra "deploy complete"               │
│                                                             │
│  При ошибке деплоя:                                        │
│    → devops: thread_send orchestra "deploy failed: <err>"   │
│    → orchestra принимает решение (retry / investigate)      │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 6: VERIFY                           │
│  qa:                                                        │
│    1. pipeline_run_acceptance (prod, scenarios=smoke only)  │
│    2. Анализ результатов                                    │
│                                                             │
│  Если smoke pass:                                           │
│    → qa: thread_send orchestra "prod verified"              │
│    → orchestra: thread_status done                          │
│    → переход к ФАЗЕ 7                                       │
│                                                             │
│  Если smoke fail:                                           │
│    → qa: thread_send orchestra "prod smoke failed"          │
│    → orchestra → devops: "rollback"                         │
│    → devops: pipeline_rollback_prod                         │
│    → qa: повторный smoke на откаченном prod                 │
│    → orchestra: задача dev на исправление                   │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    ФАЗА 7: CLEANUP                          │
│  orchestra → devops: "teardown staging <name>"              │
│  devops:                                                    │
│    1. pipeline_teardown_staging (name)                      │
│    2. thread_send orchestra "staging removed"               │
│  orchestra:                                                 │
│    1. Обновить задачу в task registry                       │
│    2. thread_status: closed                                 │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Playbook: Incident response

```
DETECT → ASSESS → ACT → VERIFY → POSTMORTEM

DETECT:
  Кто: qa (тесты), devops (healthcheck), whiner (логи)
  Как: thread_send orchestra "incident: <description>"

ASSESS:
  Кто: orchestra
  Как: pipeline_get_status prod → оценка severity
  Решение: rollback / hotfix / investigate

ACT (rollback path):
  Кто: devops
  Как: pipeline_rollback_prod
  Затем: thread_send qa "rolled back, verify"

ACT (hotfix path):
  Кто: dev → qa → devops (ускоренный цикл)
  Отличие: max 1 iteration QA, prod-деплой сразу после первого pass

VERIFY:
  Кто: qa
  Как: smoke на prod
  Результат: thread_send orchestra "resolved" или "still broken"

POSTMORTEM:
  Кто: orchestra координирует, qa + devops + dev участвуют
  Что: анализ причины, задача на preventive fix, обновление acceptance тестов
```

### 7.4 Playbook: New agent creation

```
1. orchestra: принимает решение о необходимости нового агента
2. orchestra → dev: "создай агента <role>, requirements: ..."
3. dev: создаёт manifest.yaml + system_prompt.md + tests
4. qa: проверяет что агент стартует, отвечает на healthcheck, обрабатывает event
5. devops: интегрирует в prod-стек
6. orchestra: подтверждает owner через main-secretary
```

---

## 8. Требования к обновлению System Prompts

### 8.1 orchestra

Добавить в system_prompt:
- Конкретные фазы improvement cycle с номерами
- Правило: "при получении задачи — сначала pipeline_get_status, затем plan"
- Правило: "при 3 провалах QA — эскалация, не бесконечный цикл"
- Правило: "после prod-деплоя обязательно дождаться smoke от qa"
- Правило: "при incident — сначала rollback, потом расследование"

### 8.2 dev

Добавить в system_prompt:
- Конкретные шаги: provision → code → checks → commit → report
- Правило: "всегда работать в staging, никогда в prod worktree"
- Правило: "pipeline_run_checks должен быть зелёный перед отчётом"
- Правило: "при ошибке provision — сообщить orchestra, не пытаться чинить infra"
- Список доступных pipeline-инструментов

### 8.3 qa

Добавить в system_prompt:
- Конкретные шаги: unit tests → acceptance → analyze → approve/reject
- Правило: "acceptance tests обязательны, unit tests недостаточны"
- Правило: "при reject — предоставить dev конкретный output, не абстрактное описание"
- Правило: "smoke на prod — только read-only сценарии"
- Правило: "если smoke на prod fail — немедленно сообщить orchestra"
- Список доступных pipeline-инструментов

### 8.4 devops

Добавить в system_prompt:
- Конкретные шаги: deploy → verify healthcheck → report → cleanup
- Правило: "deploy_prod только при наличии обоих approvals"
- Правило: "после rollback — обязательно дождаться qa smoke confirmation"
- Правило: "teardown staging только по указанию orchestra"
- Правило: "при failed deploy — не повторять, сообщить orchestra"
- Список доступных pipeline-инструментов

---

## 9. Порядок реализации

### Phase 1: Foundation (must-have)

1. **Acceptance test suite** — `src/core/acceptance/`
   - Scenarios 1, 2, 7, 8 (thread lifecycle, agent lifecycle, pipeline smoke, healthcheck)
   - Runner с structured output
   - Docker Compose профиль `acceptance`

2. **Deploy history tracking** — `deploy/history/prod-deploys.log`
   - Запись в log при каждом успешном deploy/rollback
   - Чтение last known-good ref

3. **Rollback script** — `deploy/rollback-prod.sh`
   - Откат на target ref или last known-good
   - Post-rollback healthcheck

### Phase 2: Agent tooling

4. **Pipeline MCP server** — `src/pipeline_mcp/`
   - Все 10 инструментов из раздела 4.2
   - Матрица доступа
   - Integration tests

5. **MCP подключение к агентам** — manifest.yaml updates
   - pipeline MCP как mcp_server для orchestra, dev, qa, devops
   - enabled_tools per agent (по матрице доступа)

### Phase 3: Agent intelligence

6. **System prompt updates** — все 4 агента
   - Playbooks из раздела 7
   - Списки инструментов из раздела 8

7. **Acceptance test расширение** — scenarios 3-6
   - Task registry, scheduler, memory, MCP connectivity

### Phase 4: Automation

8. **Post-deploy health watch** в `deploy-env.sh`
   - Автоматический rollback при unhealthy после deploy

9. **Staging age monitor**
   - whiner проверяет возраст staging-окружений
   - Уведомление orchestra при > 72h

10. **Telegram mock** для staging
    - HTTP-заглушка telegram-events для acceptance тестов без реального аккаунта

---

## 10. Метрики успеха

Система считается работающей когда:

1. **dev может** самостоятельно создать staging, написать код, прогнать checks
2. **qa может** прогнать acceptance тесты и выдать go/no-go
3. **devops может** задеплоить approved ref и откатить при проблемах
4. **orchestra может** провести полный цикл от задачи до done без ручного вмешательства
5. **Падение на любом шаге** не оставляет систему в broken state
6. **Prod acceptance smoke** проходит после каждого деплоя
7. **Rollback восстанавливает** prod за < 5 минут
8. **Owner получает уведомление** только при Level 3 (critical) инцидентах
