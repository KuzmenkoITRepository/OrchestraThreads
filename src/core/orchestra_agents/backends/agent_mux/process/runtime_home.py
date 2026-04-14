from __future__ import annotations

import shutil
from pathlib import Path

_ORCHESTRA_AGENTS_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE_AGENT_MUX_HOME = _ORCHESTRA_AGENTS_ROOT / "templates" / "agent_mux" / ".agent-mux"


def install_runtime_agent_mux_home(codex_home: Path, *, model: str) -> Path:
    runtime_home = codex_home / ".agent-mux"
    shutil.copytree(_TEMPLATE_AGENT_MUX_HOME, runtime_home, dirs_exist_ok=True)
    _install_runtime_agent_mux_model(runtime_home / "config.toml", model=model)
    return runtime_home


def _install_runtime_agent_mux_model(config_path: Path, *, model: str) -> None:
    config_text = config_path.read_text(encoding="utf-8")
    updated_text = _runtime_models_line(config_text, model=model)
    updated_text = _runtime_role_models(updated_text, model=model)
    config_path.write_text(updated_text, encoding="utf-8")


def _runtime_models_line(config_text: str, *, model: str) -> str:
    marker = "codex = ["
    line_start = config_text.find(marker)
    if line_start == -1:
        return config_text
    line_end = config_text.find("\n", line_start)
    if line_end == -1:
        line_end = len(config_text)
    original_line = config_text[line_start:line_end]
    if f'"{model}"' in original_line:
        return config_text
    updated_line = f'{original_line[:-1]}, "{model}"]'
    return config_text[:line_start] + updated_line + config_text[line_end:]


def _runtime_role_models(config_text: str, *, model: str) -> str:
    return "\n".join(_updated_role_lines(config_text, model=model))


def _updated_role_lines(config_text: str, *, model: str) -> list[str]:
    updated_lines: list[str] = []
    section_name = ""
    for line in config_text.splitlines():
        section_name, updated_line = _updated_role_line(
            line,
            section_name=section_name,
            model=model,
        )
        updated_lines.append(updated_line)
    return updated_lines


def _updated_role_line(line: str, *, section_name: str, model: str) -> tuple[str, str]:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped.strip("[]"), line
    if section_name in {"defaults", "roles.worker"} and stripped.startswith("model ="):
        return section_name, f'model = "{model}"'
    return section_name, line
