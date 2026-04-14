# AGENT MANIFESTS DOMAIN

## OVERVIEW
`agents/` = author-facing config space for managed agents. Keep manifests, prompts, agent-local assets here. Core lifecycle, runtime, Docker, backend logic live under `src/core/orchestra_agents/`.

## STRUCTURE
```text
agents/
├── dev/               # local dev agent manifest/prompt assets
├── devops/            # ops-focused agent definition
├── opencode-example/  # opencode backend example agent
├── orchestra/         # agent_mux-backed orchestration agent
├── qa/                # verification-oriented agent definition
├── secretary/         # secretary agent manifest + prompt
├── sgr/               # reusable SGR example agent
└── whiner/            # extra example/test agent definition
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Manifest shape | `*/manifest.yaml` | lifecycle wiring, backend config, runtime options |
| Prompt constraints | `*/system_prompt.md` | behavior, tool use, routing/status rules |
| Example opencode config | `opencode-example/` | clearest local opencode example |
| agent_mux example | `orchestra/manifest.yaml` | orchestration agent on mux backend |
| Shared runtime semantics | `../src/core/orchestra_agents/` | canonical schema, validation, runtime contract |

## CONVENTIONS
- Keep manifests aligned with `core.orchestra_agents` schema + registry expectations.
- Prefer nested `agent` / `runtime` / `backend` shape for new manifests. Legacy-flat fields still parse for compatibility.
- Prompts should describe routing/status/tool behavior, not duplicate platform architecture.
- Outward comms should use configured tools, callbacks, thread surfaces. Do not leak repo-internal impl detail.
- Treat this directory as definitions only. Docker/runtime behavior changes belong in `src/core/orchestra_agents/`.

## ANTI-PATTERNS
- Do not copy thread semantics, callback URLs, Docker details, backend internals into prompts unless runtime contract needs them.
- Do not let example manifests drift from shared backend contract.
- Do not treat `runtime_state/` artifacts as source for docs or architecture decisions.

## COMMANDS
```bash
curl -X POST http://127.0.0.1:8790/api/v1/registry/reload
curl -X POST http://127.0.0.1:8790/api/v1/agents/secretary/start
curl http://127.0.0.1:8790/api/v1/agents/secretary/status
```

## NOTES
- `agents/orchestra/` uses mux path.
- `agents/opencode-example/` = clearest local opencode example.
- Legacy-flat fields like `working_dir`, `http_endpoint`, `system_prompt_file`, `backend_type`, `container.*` stay supported, not preferred.
- Ignore generated paths under `agents/orchestra/runtime_state/` during repo sweeps.
