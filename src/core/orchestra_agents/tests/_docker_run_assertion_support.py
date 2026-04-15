from __future__ import annotations

from pathlib import Path

from core.orchestra_agents.tests import docker_driver_test_data as data


def flag_values(command: data.DockerCommand, flag: str) -> list[str]:
    values: list[str] = []
    for index, item in enumerate(command):
        if item == flag:
            values.append(command[index + 1])
    return values


def environment_entries(command: data.DockerCommand) -> dict[str, str]:
    entries = flag_values(command, "-e")
    return dict(entry.split("=", maxsplit=1) for entry in entries)


def expected_environment() -> dict[str, str]:
    return {
        "ORCHESTRA_AGENT_SLUG": "coding_agent",
        "ORCHESTRA_AGENT_BACKEND_TYPE": "codex_framework",
        "ORCHESTRA_AGENT_HTTP_ENDPOINT": f"http://{data.CODING_AGENT_CONTAINER}:8787",
        "ORCHESTRA_AGENT_WORKING_DIR": "/workspace/project",
        "ORCHESTRA_AGENT_ALLOWED_PEER_AGENT_SLUGS": "",
        "ORCHESTRA_AGENT_MANIFESTS_DIR": "/orchestra/agents",
        "ORCHESTRA_AGENT_MANIFEST": "/orchestra/agents/coding_agent/manifest.yaml",
        "ORCHESTRA_AGENT_SYSTEM_PROMPT_FILE": "system_prompt.md",
        "LOG_LEVEL": "DEBUG",
        "RUNTIME_TAG": (
            "coding_agent:orchestra-agent-coding_agent:codex_framework:/workspace/project"
        ),
        data.OPENAI_API_KEY: "secret",
    }


def metadata_snapshot(command: data.DockerCommand) -> dict[str, list[str]]:
    return {
        "--name": flag_values(command, "--name"),
        "--restart": flag_values(command, "--restart"),
        "--label": flag_values(command, "--label"),
        "--workdir": flag_values(command, "--workdir"),
        "--network": flag_values(command, "--network"),
        "--entrypoint": flag_values(command, "--entrypoint"),
    }


def health_command() -> str:
    return (
        'python -c "import sys,urllib.request; '
        "sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/healthz').status == 200 else 1)\""
    )


def expected_mounts(manifests_root: Path) -> list[str]:
    manifest_dir = manifests_root / "coding_agent"
    return [
        f"{manifests_root}:/orchestra/agents:ro",
        f"{manifest_dir}:/workspace/project:rw",
        f"{manifest_dir / 'logs' / 'coding_agent'}:/var/log/{data.CODING_AGENT_CONTAINER}:ro",
    ]
