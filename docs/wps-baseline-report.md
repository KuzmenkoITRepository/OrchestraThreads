# WPS violation baseline report

**Generated:** 2026-04-04
**Scope:** Active codebase (excluding `src/core/llm_proxy/`)
**Tool:** `flake8 . --select=WPS`

## Total violations: 444

## Breakdown by module area

| Area | Count | % |
|------|------:|--:|
| orchestra_thread/tests | 92 | 20.7 |
| orchestra_agents/templates | 92 | 20.7 |
| orchestra_agents/tests | 71 | 16.0 |
| agents-runtime | 67 | 15.1 |
| orchestra_thread (production) | 57 | 12.8 |
| telegram_mcp | 34 | 7.7 |
| orchestra_agents (production) | 27 | 6.1 |
| telegram_events | 4 | 0.9 |

## Breakdown by rule

| Rule | Count | Description |
|------|------:|-------------|
| WPS221 | 46 | Line complexity too high |
| WPS210 | 42 | Too many local variables |
| WPS231 | 27 | Cognitive complexity too high |
| WPS229 | 25 | Too long try body |
| WPS118 | 25 | Name shadowing builtin |
| WPS220 | 21 | Too deep nesting |
| WPS501 | 19 | finally without except |
| WPS504 | 18 | Negated condition |
| WPS214 | 18 | Too many expressions |
| WPS213 | 18 | Too many local variables |
| WPS217 | 14 | Too many await expressions |
| WPS211 | 14 | Too many arguments |
| WPS509 | 13 | Incorrectly nested ternary |
| WPS338 | 13 | Incorrect method order |
| WPS204 | 12 | Overused expression |
| WPS476 | 11 | await in for loop |
| WPS300 | 10 | Local folder import |
| WPS410 | 9 | Wrong metadata variable |
| WPS202 | 9 | Too many module members |
| WPS527 | 8 | Not a tuple used as argument |
| WPS407 | 7 | Mutable module constant |
| WPS336 | 7 | Explicit string concatenation |
| WPS230 | 7 | Too many public instance attributes |
| WPS420 | 6 | Wrong keyword: pass |
| WPS430 | 4 | Nested function |
| WPS212 | 4 | Too many return values |
| WPS201 | 4 | Too many module imports |
| WPS462 | 3 | Wrong multiline string usage |
| WPS458 | 3 | Imports collision |
| WPS441 | 3 | Control variable used after block |
| WPS327 | 3 | Useless continue |
| WPS219 | 3 | Too deep access chain |
| Other | 14 | Various low-count rules |

## Top 15 files by violation count

| File | Count |
|------|------:|
| src/core/orchestra_thread/tests/test_e2e_mvp.py | 41 |
| agents/sgr/agent_runtime/backend.py | 40 |
| src/core/orchestra_agents/tests/test_agent_mux_template.py | 35 |
| src/core/orchestra_agents/templates/agent_mux/agent_runtime/state.py | 32 |
| src/core/orchestra_agents/templates/agent_mux/agent_runtime/backend.py | 31 |
| src/core/orchestra_thread/tests/test_mcp_server.py | 24 |
| src/core/orchestra_thread/store.py | 19 |
| src/telegram_mcp/mcp_server.py | 17 |
| src/telegram_mcp/telegram_client.py | 16 |
| src/core/orchestra_thread/tests/test_agent_cli.py | 14 |
| src/core/orchestra_agents/tests/test_sgr_example.py | 14 |
| src/core/orchestra_agents/templates/agent_mux/agent_runtime/dispatch.py | 14 |
| src/core/orchestra_thread/tests/smoke_test.py | 13 |
| src/core/orchestra_agents/tests/test_docker_driver.py | 12 |
| src/core/orchestra_agents/manifest.py | 10 |

## Notes

- `src/core/llm_proxy/` is excluded from this baseline (deprecated, pending
  replacement).
- The dominant violation classes (WPS221, WPS210, WPS231) reflect concentrated
  responsibilities, large orchestration units, and procedural aggregation.
- Test files account for 37% of total violations — most are integration harness
  debt, not narrow test issues.
