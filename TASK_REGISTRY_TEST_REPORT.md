# Task Registry - Отчёт о проверке исправления

**Дата:** 2026-04-07
**Тестировщик:** Atlas (Orchestrator)
**Версия:** dev3
**Окружение:** Docker Compose (postgres + task-registry)

---

## Резюме

Проведена повторная проверка всех 10 MCP-инструментов сервиса `task_registry` после исправления сериализации.

**Статус:** ✅ **FULLY WORKING (10/10)** — оба критических бага исправлены, регрессионные интеграционные тесты добавлены.

---

## Подтверждённые исправления

### ✅ БАГ #1: UUID и datetime сериализуются в MCP-ответах

**Приоритет:** 🔴 КРИТИЧЕСКИЙ
**Статус:** ✅ ИСПРАВЛЕН

**Причина:**
`_text_result()` в `src/core/task_registry/mcp_tools.py` вызывал `json.dumps()` без encoder для `UUID` и `datetime`.

**Исправление:**
Добавлен `_json_default()`, который преобразует:
- `UUID` → строка
- `datetime` → ISO 8601 строка

**Проверка:**
Интеграционные тесты теперь используют реальный `_text_result()` без monkey-patch и успешно читают MCP-ответы с UUID-полями.

---

### ✅ БАГ #2: Artifacts возвращаются как объекты, а не JSON-строки

**Приоритет:** 🔴 КРИТИЧЕСКИЙ
**Статус:** ✅ ИСПРАВЛЕН

**Причина:**
`create_task()` и `add_artifact()` передавали в Postgres уже сериализованный JSON-текст, из-за чего `jsonb` сохранял строковые элементы внутри массива.

**Исправление:**
В `src/core/task_registry/store_tasks.py` в базу теперь передаются Python `list[dict]` и `dict`, которые `asyncpg` кодирует как настоящий JSONB.

**Проверка:**
Регрессионные тесты теперь явно проверяют, что элементы `artifacts` имеют тип `object`, а не `string`.

---

## Результаты тестирования

### ✅ Работающие функции (10/10)

| # | Инструмент | Статус | Комментарий |
|---|------------|--------|-------------|
| 1 | `task_create` | ✅ PASS | Создание задачи работает |
| 2 | `task_get` | ✅ PASS | Получение задачи по ID работает |
| 3 | `task_list` | ✅ PASS | Фильтрация по status, assignee, created_by работает |
| 4 | `task_update_status` | ✅ PASS | Обновление статуса работает |
| 5 | `task_assign` | ✅ PASS | Назначение исполнителя работает |
| 6 | `task_add_comment` | ✅ PASS | Добавление комментария работает |
| 7 | `task_add_artifact` | ✅ PASS | Артефакты возвращаются объектами |
| 8 | `task_link_thread` | ✅ PASS | Связывание с потоком работает |
| 9 | `task_get_checklist` | ✅ PASS | Получение чеклиста работает |
| 10 | `task_update_checklist` | ✅ PASS | Обновление чеклиста работает |

---

## Добавленные регрессионные проверки

В `src/core/task_registry/tests/test_integration.py` добавлены и обновлены проверки, которые делают фиксы воспроизводимыми:

1. `test_task_create_with_artifacts`
   - создаёт задачу через MCP-инструмент `task_create`
   - передаёт `artifacts` через публичный API
   - проверяет, что в ответе возвращается объект, а не строка

2. `test_task_add_artifact`
   - больше не допускает строковые артефакты
   - падает, если `artifacts[-1]` не является `dict`

3. `test_task_get_serializes_uuid_fields`
   - использует реальный `_text_result()` без monkey-patch
   - проверяет, что UUID-поля успешно сериализуются в MCP-ответах

---

## Команды для воспроизведения

```bash
# Поднять Postgres
docker compose up -d postgres

# Запустить task_registry integration suite
docker compose run --rm task-registry python -m unittest -v core.task_registry.tests.test_integration

# Очистка
docker compose down -v
```

---

## Заключение

Сервис `task_registry` теперь проходит воспроизводимую проверку по двум исходным проблемам:
- UUID/datetime корректно сериализуются в MCP-ответах
- `artifacts` возвращаются как массив объектов

Публичный путь `task_create` также принимает initial artifacts, поэтому исправление покрывает оба сценария записи артефактов: при создании задачи и при последующем добавлении.
