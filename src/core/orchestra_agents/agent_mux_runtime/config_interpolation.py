from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

ScalarVars = Mapping[str, str]
RawValues = Mapping[str, Any] | None
RawListValues = Sequence[Any] | None


class EnvNamespace:
    def __init__(self, env_dict: dict[str, str]) -> None:
        self._env = env_dict

    def __getattr__(self, name: str) -> str:
        return self._env.get(name, f"{{env.{name}}}")


class FormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def render_scalar(value: Any, variables: ScalarVars) -> str:
    env_vars = _extract_env_vars(variables)
    format_vars: MutableMapping[str, Any] = dict(variables)
    format_vars["env"] = EnvNamespace(env_vars)
    text = "" if value is None else str(value)
    formatted = FormatDict(**format_vars)
    return text.format_map(formatted)


def render_list(values: RawListValues, variables: ScalarVars) -> list[str]:
    input_values = values or []
    rendered_items: list[str] = []
    for item in input_values:
        rendered_items.append(render_scalar(item, variables))
    return rendered_items


def render_dict(values: RawValues, variables: ScalarVars) -> dict[str, str]:
    input_values = values or {}
    rendered_items: dict[str, str] = {}
    for key, item_value in input_values.items():
        rendered_items[str(key)] = render_scalar(item_value, variables)
    return rendered_items


def _extract_env_vars(variables: ScalarVars) -> dict[str, str]:
    return {
        key.replace("env.", "", 1): value
        for key, value in variables.items()
        if key.startswith("env.")
    }
