CREATE TABLE IF NOT EXISTS agents (
    agent_slug TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    event_callback_url TEXT NOT NULL,
    stop_callback_url TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    registered_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    from_agent_slug TEXT NOT NULL,
    client_request_id TEXT NOT NULL,
    operation_name TEXT NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (from_agent_slug, client_request_id)
);

CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    root_thread_id TEXT NOT NULL,
    parent_thread_id TEXT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    owner_agent_slug TEXT NOT NULL,
    participant_a_agent_slug TEXT NOT NULL,
    participant_b_agent_slug TEXT NOT NULL,
    status TEXT NOT NULL,
    last_sequence_no BIGINT NOT NULL DEFAULT 0,
    last_message_sender_agent_slug TEXT NULL,
    last_activity_at TIMESTAMPTZ NULL,
    last_inactivity_event_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    terminal_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_root_pair
ON threads(participant_a_agent_slug, participant_b_agent_slug)
WHERE parent_thread_id IS NULL AND status IN ('open', 'in_progress', 'review');

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_child_pair
ON threads(parent_thread_id, participant_a_agent_slug, participant_b_agent_slug)
WHERE parent_thread_id IS NOT NULL AND status IN ('open', 'in_progress', 'review');

CREATE INDEX IF NOT EXISTS idx_threads_root_thread_id
ON threads(root_thread_id);

CREATE INDEX IF NOT EXISTS idx_threads_parent_thread_id
ON threads(parent_thread_id);

CREATE INDEX IF NOT EXISTS idx_threads_inactivity_lookup
ON threads(last_activity_at, last_inactivity_event_at)
WHERE status NOT IN ('done', 'closed') AND last_message_sender_agent_slug IS NOT NULL;

CREATE TABLE IF NOT EXISTS thread_events (
    event_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    sequence_no BIGINT NOT NULL,
    event_kind TEXT NOT NULL,
    notification_status TEXT NULL,
    from_agent_slug TEXT NOT NULL,
    to_agent_slug TEXT NOT NULL,
    message_text TEXT NOT NULL,
    interrupts_runtime BOOLEAN NOT NULL DEFAULT FALSE,
    requires_response BOOLEAN NOT NULL DEFAULT FALSE,
    pending_delivery BOOLEAN NOT NULL DEFAULT FALSE,
    delivery_attempt_count INTEGER NOT NULL DEFAULT 0,
    next_delivery_attempt_at TIMESTAMPTZ NULL,
    delivered_at TIMESTAMPTZ NULL,
    last_delivery_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(thread_id, sequence_no)
);

CREATE INDEX IF NOT EXISTS idx_pending_events
ON thread_events(next_delivery_attempt_at, created_at)
WHERE pending_delivery = TRUE;

CREATE INDEX IF NOT EXISTS idx_thread_events_thread_sequence_desc
ON thread_events(thread_id, sequence_no DESC);
