from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.orchestra_agents.backends.opencode.backend_state import (
    Components,
    RuntimePaths,
)


@dataclass(frozen=True)
class ComponentParams:
    paths: RuntimePaths
    config: dict[str, Any]
    agent_slug: str
    working_dir: str
    serve_port: int
    ready_timeout: float


async def start_components(params: ComponentParams) -> Components:
    from core.orchestra_agents.backends.opencode.event_dispatch import (
        EventDispatcher,
    )
    from core.orchestra_agents.backends.opencode.opencode_client import (
        OpencodeClient,
    )
    from core.orchestra_agents.backends.opencode.opencode_config import (
        write_opencode_config,
    )
    from core.orchestra_agents.backends.opencode.opencode_process import (
        OpencodeProcess,
    )
    from core.orchestra_agents.backends.opencode.session_manager import (
        SessionManager,
    )

    config_path = write_opencode_config(
        params.paths.config_dir,
        params.config,
        params.agent_slug,
        params.working_dir,
    )
    process = OpencodeProcess(
        state_dir=params.paths.root,
        config_path=config_path,
        port=params.serve_port,
    )
    await process.start()
    await process.wait_ready(params.ready_timeout)
    client = OpencodeClient(base_url=f"http://127.0.0.1:{params.serve_port}")
    session_manager = SessionManager(state_dir=params.paths.state_dir, client=client)
    await session_manager.restore()
    return Components(
        process=process,
        client=client,
        session_manager=session_manager,
        dispatcher=EventDispatcher(client=client, session_manager=session_manager),
    )


async def shutdown_components(components: Components) -> None:
    if components.client is not None:
        await components.client.close()
    if components.process is not None:
        await components.process.stop()
