CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS scheduler_jobs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL CHECK (job_type IN ('cron', 'date')),
    schedule TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('agent_event', 'scheduler_wakeup')),
    action_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT true,
    auto_delete BOOLEAN NOT NULL DEFAULT false,
    misfire_policy TEXT NOT NULL DEFAULT 'skip' CHECK (misfire_policy IN ('skip', 'coalesce', 'run_all')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_at TIMESTAMPTZ NULL,
    next_run_at TIMESTAMPTZ NULL,
    run_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS scheduler_job_runs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    job_id TEXT NOT NULL REFERENCES scheduler_jobs(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    result JSONB NULL,
    error_message VARCHAR(1024) NULL,
    duration_ms INTEGER NULL
);
