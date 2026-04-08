# WPS phase 5 report

**Date:** 2026-04-08
**Phase:** 5 — final active-scope WPS sweep
**Scope:** Active codebase excluding `src/core/omniroute/**` and `src/core/wet/**`

## Outcome

The repository passes the configured WPS verification commands, but this phase is
not yet the final end-state for test-file WPS cleanup.

- `make lint` passes, including `flake8 . --select=WPS`
- `make typecheck` passes
- `make check` passes
- `docker compose --profile test run --rm test` passes in the canonical Docker test environment
- All remaining bare `# noqa: WPS...` suppressions now include inline justification comments
- Broad test-file WPS ignores still remain in `setup.cfg` and must be reduced by fixing the underlying test debt

## Active WPS status

- Baseline active WPS debt at campaign start: **444** violations (`docs/wps-baseline-report.md`)
- Current configured WPS result after this phase: **0** violations reported by `flake8 . --select=WPS`
- Remaining hidden debt still exists behind the broad test-file ignores in `setup.cfg`, especially `*/tests/*.py` and `src/core/scheduler_cron/tests/*.py`

## Governance cleanup completed in this phase

- Removed the unfinished empty per-file ignore entry from `setup.cfg`
- Added inline justification comments to the remaining WPS suppressions in integration-test files
- Preserved the documented active-scope exclusion for `omniroute` and `wet`
- Recorded that test-file ignore reduction is still required before claiming end-to-end completion

## Verification evidence

### Static verification

- `make lint`
- `make typecheck`
- `make check`

### Runtime verification

- Host-side targeted pytest failures were environment-specific (`postgres` hostname is only available in Docker networking)
- The canonical repo test command `docker compose --profile test run --rm test` was used for final verification and passed

## Remaining blocker

The task is not fully complete until the broad test-file WPS ignores in `setup.cfg`
are removed or sharply reduced by landing the underlying fixes and re-running the
verification suite against the real files.

## Notes

The repository still has an uncommitted working tree because the broader WPS refactor campaign has not been committed in this session. This report records verification status for the active repository state only; it does not create a git commit.
