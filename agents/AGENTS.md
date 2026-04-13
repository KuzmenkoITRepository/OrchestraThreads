#MW|# AGENT MANIFESTS AND EXAMPLES
#KM|
#BX|## OVERVIEW
#BS|`agents/` contains local manifests, prompts, and agent-local assets used by `orchestra_agents`; treat it as author-facing configuration space, not as the home of core platform semantics.
#BT|
#VZ|## STRUCTURE
#KM|```text
#XM|agents/
#XV|├── secretary/   # SGR-backed secretary manifest + Telegram MCP wiring
#MB|├── orchestra/   # agent_mux-backed orchestration manifest
#NK|└── sgr/         # reusable SGR Minimax manifest + prompt example
#HB|```
#BQ|
#ZV|## WHERE TO LOOK
#HR|| Task | Location | Notes |
#MX||------|----------|-------|
#WY|| Basic SGR manifest shape | `secretary/manifest.yaml`, `sgr/manifest.yaml` | lifecycle wiring + backend config |
#ZM|| Tool-only orchestration prompt rules | `orchestra/system_prompt.md`, `sgr/system_prompt.md` | concise runtime behavior constraints |
#MK|| agent_mux example | `orchestra/manifest.yaml` | optional MCP server wiring, runtime_state path |
#XJ|| Shared backend implementations | `src/core/orchestra_agents/backends/` | canonical runtime/bootstrap code for sgr, agent_mux, opencode, and example backends |
#ZP|
#RH|## CONVENTIONS
#PR|- Keep manifests aligned with `core.orchestra_agents` schema and runtime contract.
#TB|- Outward agent communication should go through configured MCP/thread tools, not plain assistant text.
#WS|- Example prompts are terse and operational; they describe routing/status behavior, not broad product vision.
#VV|- Runtime state directories are generated artifacts and should not drive architecture decisions.
#HQ|
#TH|## ANTI-PATTERNS
#QW|- Do not copy core thread or lifecycle semantics into prompts/manifests unless the runtime needs a narrow reminder.
#MM|- Do not expose runtime internals (manifests, callback URLs, thread ids, Docker state) in peer-facing messages.
#NX|- Do not treat `runtime_state/` as source material for repo guidance or code search.
#BV|- Do not let example agents diverge from the shared runtime contract without matching service/template changes.
#WV|
#TK|## COMMANDS
#BV|```bash
#SQ|curl -X POST http://127.0.0.1:8790/api/v1/registry/reload
#KK|curl -X POST http://127.0.0.1:8790/api/v1/agents/sgr/start
#RW|curl http://127.0.0.1:8790/api/v1/agents/sgr/status
#VS|```
#BH|
#XM|## NOTES
#ZJ|- `agents/orchestra/` uses `agent_mux`; `agents/secretary/` and `agents/sgr/` use the SGR runtime path.
#BN|- Ignore unreadable/generated paths under `agents/orchestra/runtime_state/` during repo analysis.
#HM|- Backend entrypoints now come from `src/core/orchestra_agents/backends/`; `agents/*/` should not contain `agent_runtime/` packages.
