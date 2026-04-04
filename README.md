# Orchestra

This repository is the base for the next `orchestra` iteration.

`OrchestraThreads` now lives as a self-contained core module in `src/core/orchestra_thread`.

`OrchestraAgents` now lives as a separate lifecycle module in `src/core/orchestra_agents`.

`LLMProxy` now lives as a separate routing module in `src/core/llm_proxy`.

Main entry points:

- service code: `src/core/orchestra_thread`
- service docs: `src/core/orchestra_thread/docs/README.md`
- architecture draft: `src/core/orchestra_thread/docs/ARCH-DRAFT.md`
- MCP draft: `src/core/orchestra_thread/docs/MCP-INTEGRATION-DRAFT.md`
- tests: `src/core/orchestra_thread/tests`
- lifecycle service code: `src/core/orchestra_agents`
- lifecycle docs: `src/core/orchestra_agents/docs/README.md`
- lifecycle tests: `src/core/orchestra_agents/tests`
- llm proxy code: `src/core/llm_proxy`
- llm proxy docs: `src/core/llm_proxy/docs/README.md`
- llm proxy tests: `src/core/llm_proxy/tests`

Infrastructure:

- runtime stack: `docker-compose.yml`
- database: Postgres in a dedicated container
- service: `orchestra-threads` container
- agent lifecycle service: `orchestra-agents` container
- llm routing service: `llm-proxy` container
- tests: Docker-only, against Postgres

Docker test suite:

```bash
docker compose --profile test run --rm test
```
