# Orchestra

This repository is the base for the next `orchestra` iteration.

`OrchestraThreads` now lives as a self-contained core module in `src/core/orchestra_thread`.

`OrchestraAgents` now lives as a separate lifecycle module in `src/core/orchestra_agents`.


Infrastructure:

- runtime stack: `docker-compose.yml`
- database: Postgres in a dedicated container
- service: `orchestra-threads` container
- agent lifecycle service: `orchestra-agents` container
- llm routing: `orchestra-omniroute` container
- tests: Docker-only, against Postgres

Docker test suite:

```bash
docker compose --profile test run --rm test
```
