from __future__ import annotations

INSERT_JOB_SQL = """
INSERT INTO scheduler_jobs (
    name, job_type, schedule, action_type, action_payload,
    enabled, auto_delete, misfire_policy, created_by, metadata,
    last_run_at, next_run_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
RETURNING id
"""
SELECT_JOB_BY_NAME_SQL = "SELECT * FROM scheduler_jobs WHERE name = $1"
SELECT_JOB_BY_ID_SQL = "SELECT * FROM scheduler_jobs WHERE id = $1"
DELETE_JOB_SQL = "DELETE FROM scheduler_jobs WHERE name = $1"
UPDATE_ROW_SQL_SUFFIX = " 1"
