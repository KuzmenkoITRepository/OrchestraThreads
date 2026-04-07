from __future__ import annotations

from core.scheduler_cron.bootstrap_data import job_definitions as _job_definitions
from core.scheduler_cron.bootstrap_ops import bootstrap_jobs as bootstrap_jobs

BOOTSTRAP_JOBS = _job_definitions()
