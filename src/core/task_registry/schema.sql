CREATE TABLE IF NOT EXISTS tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT NOT NULL,
    description         TEXT,
    status              TEXT NOT NULL DEFAULT 'draft',
    assignee            TEXT,
    created_by          TEXT NOT NULL,
    priority            TEXT DEFAULT 'normal',
    acceptance_criteria TEXT,
    linked_thread_id    UUID,
    blocked_by          UUID[],
    artifacts           JSONB DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_checklist_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    label       TEXT NOT NULL,
    checked     BOOLEAN NOT NULL DEFAULT false,
    checked_by  TEXT,
    checked_at  TIMESTAMPTZ,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_comments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    author      TEXT NOT NULL,
    body        TEXT NOT NULL,
    artifacts   JSONB DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status);

CREATE INDEX IF NOT EXISTS idx_tasks_assignee
    ON tasks(assignee);

CREATE INDEX IF NOT EXISTS idx_tasks_created_by
    ON tasks(created_by);

CREATE INDEX IF NOT EXISTS idx_task_checklist_items_task_id
    ON task_checklist_items(task_id);

CREATE INDEX IF NOT EXISTS idx_task_comments_task_id
    ON task_comments(task_id);
