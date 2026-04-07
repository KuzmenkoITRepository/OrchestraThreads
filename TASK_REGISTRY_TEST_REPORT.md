# Task Registry - Отчёт о ручном тестировании

**Дата:** 2026-04-07
**Тестировщик:** Atlas (Orchestrator)
**Версия:** dev3
**Окружение:** Docker Compose (postgres + task-registry)

---

## Резюме

Проведено полное ручное тестирование всех 10 MCP-инструментов сервиса `task_registry`.

**Статус:** ⚠️ **ЧАСТИЧНО РАБОТАЕТ** - 9/10 инструментов функциональны, найдены 2 критических бага

---

## Результаты тестирования

### ✅ Работающие функции (9/10)

| # | Инструмент | Статус | Комментарий |
|---|------------|--------|-------------|
| 1 | `task_create` | ✅ PASS | Создание задачи с чеклистом работает |
| 2 | `task_get` | ✅ PASS | Получение задачи по ID работает |
| 3 | `task_list` | ✅ PASS | Фильтрация по status, assignee, created_by работает |
| 4 | `task_update_status` | ✅ PASS | Обновление статуса работает |
| 5 | `task_assign` | ✅ PASS | Назначение исполнителя работает |
| 6 | `task_get_checklist` | ✅ PASS | Получение чеклиста работает |
| 7 | `task_update_checklist` | ✅ PASS | Обновление элемента чеклиста работает |
| 8 | `task_add_comment` | ✅ PASS | Добавление комментария работает |
| 9 | `task_add_artifact` | ⚠️ PARTIAL | Работает, но возвращает некорректные данные |
| 10 | `task_link_thread` | ✅ PASS | Связывание с потоком работает |

### ❌ Найденные баги

#### БАГ #1: UUID не сериализуется в JSON (ИСПРАВЛЕН)

**Приоритет:** 🔴 КРИТИЧЕСКИЙ
**Статус:** ✅ ИСПРАВЛЕН

**Описание:**
При возврате результатов через MCP все UUID-поля вызывали ошибку:
```
TypeError: Object of type UUID is not JSON serializable
```

**Причина:**
В `mcp_tools.py` функция `_text_result` использовала `json.dumps()` без custom encoder для UUID и datetime.

**Исправление:**
Добавлен custom JSON encoder в `src/core/task_registry/mcp_tools.py`:
```python
def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

def _text_result(payload: JsonDict) -> JsonDict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=_json_default)}]}
```

**Проверка:**
После исправления все UUID корректно сериализуются в строки.

---

#### БАГ #2: Artifacts возвращаются как массив строк вместо объектов

**Приоритет:** 🔴 КРИТИЧЕСКИЙ
**Статус:** ❌ НЕ ИСПРАВЛЕН

**Описание:**
При добавлении артефакта через `task_add_artifact` и последующем получении задачи через `task_get`, поле `artifacts` содержит массив JSON-строк вместо массива объектов:

```python
# Ожидается:
"artifacts": [
    {"url": "...", "type": "image", "label": "..."}
]

# Фактически возвращается:
"artifacts": [
    '{"url": "...", "type": "image", "label": "..."}'
]
```

**Причина:**
В `src/core/task_registry/store_tasks.py` на строке 174:
```python
SET artifacts = COALESCE(artifacts, '[]'::jsonb) || jsonb_build_array($2::jsonb)
```

Параметр `$2` передаётся как JSON-строка (`json.dumps(artifact)`), а затем приводится к `jsonb`. Postgres интерпретирует это как строку внутри JSONB-массива.

**Воспроизведение:**
```python
# 1. Создать задачу
task_create(title="Test", created_by="tester")

# 2. Добавить артефакт
task_add_artifact(task_id="...", artifact={"url": "test.png", "type": "image"})

# 3. Получить задачу
task = task_get(task_id="...")
print(task["artifacts"])  # ['{"url": "test.png", "type": "image"}']
```

**Решение:**
Изменить `store_tasks.py:169-180`:
```python
async def add_artifact(self, task_id: str, artifact: dict[str, Any]) -> bool:
    assert self.pool is not None
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tasks
            SET artifacts = COALESCE(artifacts, '[]'::jsonb) || $2::jsonb,
                updated_at = NOW()
            WHERE id = $1
            RETURNING 1
            """,
            task_id,
            json.dumps(artifact),  # Передаём JSON-строку, но без jsonb_build_array
        )
    return row is not None
```

Или лучше:
```python
async def add_artifact(self, task_id: str, artifact: dict[str, Any]) -> bool:
    assert self.pool is not None
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tasks
            SET artifacts = artifacts || $2::jsonb,
                updated_at = NOW()
            WHERE id = $1
            RETURNING 1
            """,
            task_id,
            json.dumps([artifact]),  # Передаём массив с одним элементом
        )
    return row is not None
```

**Аналогичная проблема:**
В `create_task` (строка 31) тоже используется `json.dumps(list(artifacts or []))`, что может вызвать похожие проблемы.

---

## Детальные результаты тестов

### TEST 1: task_create ✅
```
Created task ID: e320f677-ca4c-4b98-89de-79c021deed18
Title: Manual Test Task
Status: draft
Priority: high
Created by: manual-tester
Checklist items: 3 (Step 1, Step 2, Step 3)
```

### TEST 2: task_get ✅
```
Retrieved task ID: e320f677-ca4c-4b98-89de-79c021deed18
Title: Manual Test Task
Description: This is a test task created manually
Status: draft
```

### TEST 3: task_list ✅
```
Total tasks found: 3
Draft tasks: 3
Tasks by manual-tester: 3
```

### TEST 4: task_update_status ✅
```
Update result: True
New status: in_progress
```

### TEST 5: task_assign ✅
```
Assign result: True
Assignee: test-agent-007
```

### TEST 6: task_get_checklist ✅
```
Checklist items count: 3
  1. [f24312d7-fedd-4ce0-bf7c-6167f624294b] Step 1: Initialize - Checked: False
  2. [ed341abe-c676-41c4-92b5-f43191e5a398] Step 2: Execute - Checked: False
  3. [f98ff5db-f667-4412-ab96-f31fd9966e07] Step 3: Verify - Checked: False
```

### TEST 7: task_update_checklist ✅
```
Update result: True
Item checked: True
Checked by: manual-tester
```

### TEST 8: task_add_comment ✅
```
Comment ID: 199d5c83-a73e-46fb-b97a-a72f6a5fae47
Author: manual-tester
Body: This is a test comment with some important notes.
Artifacts: 1 (Documentation PDF)
```

### TEST 9: task_add_artifact ⚠️
```
Add artifact result: True
Total artifacts: 2

❌ ОШИБКА: artifacts возвращаются как массив строк:
['[]', '{"url": "https://example.com/screenshot.png", "type": "image", "label": "Test Screenshot"}']

Ожидалось:
[{"url": "https://example.com/screenshot.png", "type": "image", "label": "Test Screenshot"}]
```

### TEST 10: task_link_thread ✅
```
Link thread result: True
Linked thread ID: 12345678-1234-5678-1234-567812345678
```

### TEST 11: Error Handling ✅
```
Non-existent task error: Task not found: 00000000-0000-0000-0000-000000000000
Missing parameter error: Missing required parameter: title
Invalid tool error: Unknown tool: task_invalid_tool
```

---

## Дополнительные проверки

### HTTP API
- ✅ `/healthz` endpoint работает корректно
- ✅ Возвращает `{"status": "ok"}` при здоровом состоянии

### База данных
- ✅ Postgres подключение работает
- ✅ Схема `public` создаётся автоматически
- ✅ Все таблицы создаются корректно:
  - `tasks`
  - `task_checklist_items`
  - `task_comments`
- ✅ Индексы созданы
- ✅ Foreign keys работают (CASCADE DELETE)

### Docker интеграция
- ✅ Сервис запускается через `docker compose`
- ✅ Healthcheck работает
- ✅ Зависимость от postgres корректна
- ✅ Порт 8791 (маппинг на 8991) доступен

---

## Рекомендации

### Критические исправления (MUST FIX)

1. **БАГ #2: Исправить сериализацию artifacts**
   - Файл: `src/core/task_registry/store_tasks.py`
   - Метод: `add_artifact` (строка 167-182)
   - Приоритет: 🔴 ВЫСОКИЙ
   - Блокирует: Корректную работу с артефактами

2. **Проверить create_task с artifacts**
   - Файл: `src/core/task_registry/store_tasks.py`
   - Метод: `create_task` (строка 16-72)
   - Убедиться, что artifacts при создании задачи тоже корректно сериализуются

### Улучшения (SHOULD FIX)

3. **Добавить интеграционные тесты для artifacts**
   - Текущие тесты в `tests/test_integration.py` не покрывают этот кейс
   - Добавить тест, который проверяет структуру возвращаемых artifacts

4. **Улучшить обработку ошибок**
   - Добавить валидацию структуры artifact перед добавлением
   - Проверять наличие обязательных полей (`url`, `type`)

5. **Документация**
   - Добавить примеры использования MCP-инструментов
   - Документировать формат artifacts

### Оптимизации (NICE TO HAVE)

6. **Добавить bulk операции**
   - `task_bulk_create` - создание нескольких задач
   - `task_bulk_update_status` - массовое обновление статусов

7. **Расширить фильтрацию**
   - Фильтрация по priority
   - Фильтрация по linked_thread_id
   - Поиск по тексту в title/description

---

## Заключение

Сервис `task_registry` **функционален на 90%**. Основной функционал работает корректно:
- ✅ Создание и управление задачами
- ✅ Чеклисты
- ✅ Комментарии
- ✅ Назначение и статусы
- ✅ Связывание с потоками

**Критический баг с artifacts блокирует production-ready статус.**

После исправления БАГ #2 сервис будет готов к использованию в production.

---

## Приложения

### Тестовый скрипт
Полный тестовый скрипт доступен в: `/home/odinykt/projects/orchestra-dev/OrchestraThreads-3/test_task_registry_manual.py`

### Команды для воспроизведения
```bash
# Запуск стека
docker compose up -d postgres task-registry

# Проверка здоровья
curl http://localhost:8991/healthz

# Запуск тестов
docker compose exec task-registry python3 /app/test_task_registry_manual.py

# Очистка
docker compose down -v
```

### Версии
- Python: 3.11.15
- Postgres: 16-alpine
- asyncpg: (из requirements.txt)
- Docker Compose: v2.x
