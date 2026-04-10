# Front 2 — agent lifecycle, manifest, registry, and platform contract layer

## Front mission

**Historical note:** legacy proxy routing has been replaced by `omniroute` + `wet`.

This front reduces active WPS debt in the non-thread `orchestra_agents`
platform surface: manifests, registry, lifecycle routes, runtime contract, and
Docker/platform integration.

`src/core/omniroute/**` and `src/core/wet/**` are not part of this front.

## Front work scope

Platform modules:

- `src/core/orchestra_agents/manifest.py`
- `src/core/orchestra_agents/registry.py`
- `src/core/orchestra_agents/service_routes.py`
- `src/core/orchestra_agents/service_main.py`
- `src/core/orchestra_agents/runtime/backend.py`
- `src/core/orchestra_agents/runtime/contracts.py`
- `src/core/orchestra_agents/scaffold.py`
- `src/core/orchestra_agents/docker_driver/driver.py`

Related test files owned by this front:

- `src/core/orchestra_agents/tests/test_docker_driver.py`
- `src/core/orchestra_agents/tests/test_manifest_registry.py`
- `src/core/orchestra_agents/tests/test_runtime_contract.py`
- `src/core/orchestra_agents/tests/test_service.py`
- `src/core/orchestra_agents/tests/test_scaffold.py`

## Current state

Current observed state of this front:

- the largest remaining platform hotspots are in `manifest.py`,
  `service_routes.py`, `runtime/backend.py`, and `registry.py`;
- the debt here mostly reflects broad service/platform responsibilities rather
  than duplicated example-runtime logic;
- some lifecycle-facing tests still carry substantial orchestration/setup noise
  and should be refactored together with the production contracts they cover.

## System solution concept

The system solution for this front is to make the lifecycle platform explicit by
role:

1. manifest normalization stays separate from registry state and service route
   handling;
2. runtime contract behavior stays separate from lifecycle API orchestration;
3. Docker driver and scaffold logic remain utility surfaces, not hidden service
   policy containers;
4. tests for these concerns mirror those same boundaries instead of recreating
   full service orchestration inline.

## Implementation shape

This front should prefer these transformations:

- split parsing/normalization from lifecycle orchestration;
- extract route-family request handling without changing public endpoints;
- keep runtime contract logic small and explicit;
- reduce test complexity by extracting stable fixtures and request builders.

This front must not:

- refactor shared `agent_mux` execution internals owned by Front 1;
- edit thread semantics or thread-owned APIs owned by Front 3;
- bring `omniroute` or `wet` back into the active remediation scope.

## Completion signal

This front is complete when lifecycle/registry/platform modules and their owned
tests are WPS-clean on their owned files and the remaining debt is no longer
centered in broad lifecycle aggregators.
