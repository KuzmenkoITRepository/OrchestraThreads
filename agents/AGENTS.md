# AGENT MANIFESTS DOMAIN

## OVERVIEW
`agents/` is author-facing configuration space for managed agents. Keep only manifests, prompts, and agent-local assets here. Core lifecycle, runtime, Docker, and backend logic live under `src/core/orchestra_agents/`.

## STRUCTURE
```text
agents/
├── dev/               # local dev agent manifest/prompt assets
├── devops/            # operations-focused agent definition
├── opencode-example/  # opencode backend example agent
├── orchestra/         # agent_mux-backed orchestration agent
├── qa/                # verification-oriented agent definition
├── secretary/         # secretary agent manifest and prompt
├── sgr/               # reusable SGR example agent
└── whiner/            # additional example/test agent definition
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Manifest shape | `*/manifest.yaml` | lifecycle wiring, backend config, runtime options |
| Prompt constraints | `*/system_prompt.md` | terse operational behavior, tool usage expectations |
| Example opencode config | `opencode-example/` | reference manifest for opencode-backed agents |
| agent_mux example | `orchestra/manifest.yaml` | orchestration agent using mux backend |
| Shared runtime semantics | `../src/core/orchestra_agents/` | canonical schema, validation, runtime contract |

## CONVENTIONS
- Keep manifests aligned with `core.orchestra_agents` schema and registry expectations.
- Prompts should describe routing/status/tool behavior, not duplicate platform architecture.
- Outward communication should go through configured tools, callbacks, or thread surfaces — not repo-internal implementation detail.
- Treat this directory as definitions-only. If you need Docker/runtime behavior, change `src/core/orchestra_agents/` instead.

## ANTI-PATTERNS
- Do not copy thread semantics, callback URLs, Docker details, or backend internals into prompts unless the runtime contract truly needs them.
- Do not let example manifests drift away from the shared backend contract.
- Do not treat `runtime_state/` artifacts as source material for docs or architectural decisions.

## COMMANDS
```bash
curl -X POST http://127.0.0.1:8790/api/v1/registry/reload
curl -X POST http://127.0.0.1:8790/api/v1/agents/secretary/start
curl http://127.0.0.1:8790/api/v1/agents/secretary/status
```

## NOTES
- `agents/orchestra/` uses the mux path; `agents/opencode-example/` is the clearest local opencode example.
- Ignore generated paths under `agents/orchestra/runtime_state/` during repo sweeps.
