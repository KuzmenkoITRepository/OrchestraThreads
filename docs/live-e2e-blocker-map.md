# Live E2E blocker map

## Scope

This document captures the concrete blockers found while running live dev E2E across real manifests and real thread flows.

## High-level answer on wet

The current opencode failures are **not** best explained as "because requests go through wet" in the abstract.

The grounded repo-visible issue is more specific:

- several opencode manifests explicitly point runtime traffic at `OMNIROUTE_URL=http://host.docker.internal:8100`
- that path is the wet-facing host route
- the same runtime bearer key works correctly against direct in-network OmniRoute `http://orchestra-omniroute:20128`
- bearer auth against `http://host.docker.internal:8100` returned an empty model list and `Invalid API key` failures in live opencode runtimes

So the actionable problem is the **configured auth plane / base URL**, not merely the existence of wet in the stack.

## Issues encountered

### 1. Secretary SGR MCP manifest mismatch

Status: fixed

- `agents/secretary/manifest.yaml` mixed SGR inline MCP entries with subprocess-style MCP entries.
- `sgr_minimax` only loads inline `module/class/schema_fn` MCP definitions.
- Fix applied earlier:
  - normalized secretary thread/memory MCP wiring to SGR inline form
  - added `orchestra_memory_tool_definitions()` export
  - tightened backend-specific `mcp_servers` validation

## 2. agent_mux route generation bug

Status: fixed

- `agent_mux` built `http://.../minimax/v1/responses` for `minimax_only`.
- OmniRoute serves `/v1/responses`, not `/minimax/v1/responses`.
- Fix applied earlier in `src/core/orchestra_agents/backends/agent_mux/config/codex_helpers.py`.

## 3. Orchestra model qualification bug

Status: fixed

- `agents/orchestra/manifest.yaml` used `MiniMax-M2.7` without provider prefix.
- OmniRoute required `minimax/MiniMax-M2.7`.
- Fix applied earlier in source and dev worktree.

## 4. Dev OmniRoute runtime key mismatch

Status: fixed

- Dev OmniRoute had provider connections but no valid runtime API key row.
- Generated Codex config correctly used `env_key = "OMNIROUTE_API_KEY"`, but the stored key was invalid.
- Fix applied operationally:
  - created a fresh dev runtime API key through `/api/keys`
  - wrote it back to Vault
  - re-rendered dev env through canonical deploy

## 5. Codex `web_search` Responses incompatibility

Status: fixed

- Codex default Responses payload included `web_search`.
- OmniRoute rejected that tool type.
- Fix applied in generated Codex config via top-level:
  - `web_search = "disabled"`

## 6. `thread_current.allowed_actions` mismatch with service enforcement

Status: fixed

- `thread_current` originally advertised `thread_send` / `thread_status` based only on thread role/status.
- Actual service enforcement also applies `allowed_peer_agent_slugs`.
- This caused `human -> orchestra` flows to over-promise reply actions that the service later rejected.
- Fix applied:
  - `src/core/orchestra_thread/mcp_thread_view_current.py` now filters `allowed_actions` using the same peer allowlist source as `thread_peers`
  - regression added in `src/core/orchestra_thread/tests/test_mcp_server.py`

## 7. Current shared opencode blocker

Status: open before normalization in this document

Grounded live evidence showed that:

- `dev`, `devops`, `qa`, and `opencode-example` all used:
  - `OMNIROUTE_URL: http://host.docker.internal:8100`
  - `model: cx/gpt-5.4-mini`
- Their runtime DBs recorded repeated failures against:
  - `http://host.docker.internal:8100/v1/chat/completions`
  - `Invalid API key`
- The **same** runtime API key worked correctly against direct in-network OmniRoute:
  - `http://orchestra-omniroute:20128/v1/models`

Conclusion: the 8100 host route is the wrong runtime auth path for these opencode agents.

## 8. Current whiner-specific blocker

Status: open before normalization in this document

`whiner` diverged from the otherwise shared opencode shape:

- `model: omo`
- `runtime.env.LLM_PROXY_URL: http://host.docker.internal:8100`
- no `OMNIROUTE_URL`

Live runtime evidence showed repeated:

- `No credentials for provider: openai`

Conclusion: `whiner` needs both route normalization and model normalization to a known-good GPT path.

## 9. Current SGR-specific blocker

Status: still open

`sgr` is no longer blocked by thread-owner callback shape, but it still shows a backend-specific no-action symptom:

- receives events
- executes `reasoning_tool` and `final_answer_tool`
- logs `SGR turn without action`
- emits no outward thread message/status

This is separate from the opencode fixes and should be debugged independently.

## Proven live outcomes so far

### Proven successful/terminal cases

- `secretary -> orchestra`
  - produced a real orchestra-authored child-thread reply
  - child thread reached `done`
  - root thread later closed cleanly
- `orchestra -> dev`
- `orchestra -> devops`
- `orchestra -> qa`
  - all reached terminal `closed` state with orchestra-authored close notifications after inactivity

### Structurally poor historical proof paths

- `human -> whiner`
- `human -> opencode-example`
- `human -> sgr`

These were poor proof paths because inactivity callbacks targeted `human`, which has no event callback endpoint.

## Durable config direction

To prevent the same opencode failures from reappearing:

1. normalize opencode manifests away from `http://host.docker.internal:8100`
2. use direct in-network OmniRoute `http://orchestra-omniroute:20128`
3. use a known-good GPT model like `cx/gpt-5.4-mini`
4. update the opencode template as well as live/source manifests so the fix persists

## Remaining work after config normalization

- re-run live opencode matrix cases on the normalized route:
  - `whiner -> opencode-example`
  - `opencode-example -> sgr`
  - `sgr -> whiner`
- continue separate debugging for the SGR no-action symptom if it remains after reroute-driven noise is removed
