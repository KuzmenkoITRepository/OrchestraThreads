CREATE TABLE IF NOT EXISTS agent_log_events (
    event_id            TEXT PRIMARY KEY,
    event_type          TEXT NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    received_at         TIMESTAMPTZ NOT NULL,
    agent_slug          TEXT NOT NULL,
    run_id              TEXT,
    thread_id           TEXT,
    correlation_id      TEXT,
    parent_event_id     TEXT,
    status              TEXT,
    model_name          TEXT,
    provider_name       TEXT,
    request_kind        TEXT,
    action_kind         TEXT,
    target_name         TEXT,
    target_agent_slug   TEXT,
    latency_ms          INTEGER,
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_json        JSONB NOT NULL,
    raw_payload_attached BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS agent_log_event_labels (
    event_id    TEXT NOT NULL REFERENCES agent_log_events(event_id) ON DELETE CASCADE,
    label_key   TEXT NOT NULL,
    label_value TEXT NOT NULL,
    PRIMARY KEY (event_id, label_key)
);

CREATE TABLE IF NOT EXISTS agent_log_raw_logs (
    log_id          BIGSERIAL PRIMARY KEY,
    event_id        TEXT REFERENCES agent_log_events(event_id) ON DELETE SET NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL,
    agent_slug      TEXT NOT NULL,
    run_id          TEXT,
    thread_id       TEXT,
    correlation_id  TEXT,
    source          TEXT,
    level           TEXT NOT NULL,
    raw_message     TEXT NOT NULL,
    raw_payload_json JSONB
);

CREATE INDEX IF NOT EXISTS agent_log_events_agent_time_idx
    ON agent_log_events(agent_slug, occurred_at DESC, event_id DESC);

CREATE INDEX IF NOT EXISTS agent_log_events_corr_idx
    ON agent_log_events(agent_slug, correlation_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS agent_log_events_run_idx
    ON agent_log_events(agent_slug, run_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS agent_log_events_thread_idx
    ON agent_log_events(agent_slug, thread_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS agent_log_events_status_idx
    ON agent_log_events(agent_slug, status, occurred_at DESC);

CREATE INDEX IF NOT EXISTS agent_log_event_labels_lookup_idx
    ON agent_log_event_labels(label_key, label_value, event_id);

CREATE INDEX IF NOT EXISTS agent_log_raw_logs_agent_time_idx
    ON agent_log_raw_logs(agent_slug, occurred_at DESC, log_id DESC);

CREATE INDEX IF NOT EXISTS agent_log_raw_logs_corr_idx
    ON agent_log_raw_logs(agent_slug, correlation_id, occurred_at DESC, log_id DESC);
