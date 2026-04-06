# WPS refactor governance rules

**Historical note:** `llm-proxy` has been replaced by `omniroute` + `wet`.

This document codifies the rules governing the WPS remediation campaign.

## Excluded scope

`src/core/omniroute/` and `src/core/wet/` are excluded from the active WPS campaign. It is
deprecated and pending replacement by an external solution. Its violations are
not tracked in the active baseline.

## Anti-patterns (forbidden)

### No cosmetic facade files

Do not create wrapper files that move complexity from one module to another
without reducing total subsystem complexity. A file split is acceptable only
when both conditions are true:

1. The split reduces coupling and clarifies module responsibilities.
2. The split reduces total subsystem complexity instead of merely relocating WPS
   violations.

### No general-purpose dumping grounds

Do not create `utils.py`, `helpers.py`, or similarly named catch-all modules.
Every extracted module must have a single, coherent operational purpose.

### No `# noqa` without justification

Every `# noqa: WPSxxx` must include a brief inline comment explaining why the
suppression is necessary. Prefer refactoring over suppression.

### No type safety shortcuts

Do not use `# type: ignore` without an explicit justification comment. Do not
introduce `Any` types without documented reasoning.

## Backward compatibility

Public module surfaces that are already imported by other modules must remain
backward-compatible throughout the campaign. When a module is split, the
original module must re-export the public names until all downstream consumers
are migrated.

## Commit convention

Each refactoring commit must follow this format:

```
<type>(phase-N): <description>
```

Where `<type>` is one of: `refactor`, `test`, `docs`, `chore`.

## Verification protocol

Every structural change must pass before proceeding:

1. `make format` — code formatted
2. `make lint` — ruff + WPS checks
3. `make typecheck` — mypy --strict
4. Relevant tests — pytest on affected modules

The full check can be run with `make check`.

## Rollback strategy

Each phase is designed to be independently reversible. If a phase introduces
regressions that cannot be resolved within reasonable effort, revert the phase
and re-plan before retrying.

## Progress tracking

WPS violation counts are recorded at the end of each phase in a dedicated
report file: `docs/wps-phaseN-report.md`. These reports track violations by
module area, by rule, and by file, enabling phase-over-phase comparison.
