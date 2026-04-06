# AGENT MANIFESTS AND EXAMPLES

## OVERVIEW
`agents/` contains local manifests, prompts, and runnable runtime examples used by `orchestra_agents`; treat it as configuration-plus-example-runtime space, not as the home of core platform semantics.

## STRUCTURE
```text
agents/
├── secretary/   # SGR-backed secretary manifest + Telegram MCP wiring
├── orchestra/   # agent_mux-backed orchestration example
└── sgr/         # reusable SGR Minimax example runtime (with support/ submodule)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Basic SGR manifest shape | `secretary/manifest.yaml`, `sgr/manifest.yaml` | lifecycle wiring + backend config |
| Tool-only orchestration prompt rules | `orchestra/system_prompt.md`, `sgr/system_prompt.md` | concise runtime behavior constraints |
| agent_mux example | `orchestra/manifest.yaml` | optional MCP server wiring, runtime_state path |
| Secretary with Telegram MCP | `secretary/manifest.yaml` | MCP server block for `telegram_mcp` integration |
| Example runtime implementation | `sgr/agent_runtime/` | largest example backend in repo (with `support/` helpers) |

## CONVENTIONS
- Keep manifests aligned with `core.orchestra_agents` schema and runtime contract.
- Outward agent communication should go through configured MCP/thread tools, not plain assistant text.
- Example prompts are terse and operational; they describe routing/status behavior, not broad product vision.
- Runtime state directories are generated artifacts and should not drive architecture decisions.

## ANTI-PATTERNS
- Do not copy core thread or lifecycle semantics into prompts/manifests unless the runtime needs a narrow reminder.
- Do not expose runtime internals (manifests, callback URLs, thread ids, Docker state) in peer-facing messages.
- Do not treat `runtime_state/` as source material for repo guidance or code search.
- Do not let example agents diverge from the shared runtime contract without matching service/template changes.

## COMMANDS
```bash
curl -X POST http://127.0.0.1:8790/api/v1/registry/reload
curl -X POST http://127.0.0.1:8790/api/v1/agents/sgr/start
curl http://127.0.0.1:8790/api/v1/agents/sgr/status
```

## NOTES
- `agents/orchestra/` uses `agent_mux`; `agents/secretary/` and `agents/sgr/` use the SGR runtime path.
- Ignore unreadable/generated paths under `agents/orchestra/runtime_state/` during repo analysis.
- `secretary` integrates `telegram_mcp` MCP server for outbound Telegram messaging via manifest wiring.
