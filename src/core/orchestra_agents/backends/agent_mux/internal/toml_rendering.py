from __future__ import annotations

import json


def toml_quote(value: str) -> str:
    return json.dumps(str(value))


def toml_bool(value: bool) -> str:
    return "true" if bool(value) else "false"
