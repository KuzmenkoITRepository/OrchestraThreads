# Front 1 — agent runtime, template, and example-agent execution layer

## Front mission

This front reduces active WPS debt in the shared execution layer used by
`agent_mux`, template runtimes, and example agents. It is responsible for the
runtime engine shape, template adapter shape, and example-agent runtime reuse.

`src/core/llm_proxy/**` is not part of this front.

## Front work scope

Production/runtime modules:

- `src/core/orchestra_agents/agent_mux_runtime/**`
- `src/core/orchestra_agents/templates/agent_mux/agent_runtime/**`
- `agents/orchestra/agent_runtime/**`
- `agents/secretary/agent_runtime/**`
- `agents/sgr/agent_runtime/**`

Related tests owned by this front:

- `src/core/orchestra_agents/tests/test_agent_mux_template.py`
- `src/core/orchestra_agents/tests/test_agent_mux_runtime_parity.py`
- `src/core/orchestra_agents/tests/test_sgr_example.py`

## Current state

Current observed state of this front:

- the shared `agent_mux` runtime/parity slice has already been cleaned and
  locally verified;
- the heaviest remaining hotspots are still concentrated in:
  - `agents/sgr/agent_runtime/backend.py`
  - `agents/sgr/agent_runtime/main.py`
  - `agents/sgr/agent_runtime/support.py`
  - `src/core/orchestra_agents/templates/agent_mux/agent_runtime/backend.py`
  - `src/core/orchestra_agents/tests/test_agent_mux_template.py`
- the dominant remaining signals are concentrated runtime objects, duplicated
  orchestration logic, and scenario-heavy integration test harness code.

## System solution concept

The system solution for this front is to make the execution layer truly shared
 and role-based:

1. shared queue/context/dispatch behavior lives only in
   `src/core/orchestra_agents/agent_mux_runtime/**`;
2. template runtime files become thin adapters over that shared runtime;
3. example agents reuse the shared runtime instead of carrying their own heavy
   orchestration logic;
4. runtime tests validate shared behavior once, while example tests validate
   only adapter-specific intent.

## Implementation shape

This front should prefer these transformations:

- extract role-coherent runtime stores and dispatch units;
- replace duplicated runtime flows in examples with shared adapters;
- shrink template files into compatibility shims over shared runtime logic;
- extract test harness helpers for backend startup, fake binaries, polling, and
  capture loading.

This front must not:

- move runtime complexity into generic `helpers.py`-style dumping grounds;
- change lifecycle service routes or manifest schema owned by Front 2;
- pull `llm_proxy` into active refactoring work.

## Completion signal

This front is complete when the runtime/template/example-agent layer and its
owned tests are WPS-clean on their owned files and the remaining WPS debt is no
longer dominated by duplicated execution logic.
