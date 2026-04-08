from __future__ import annotations

from typing import TypeAlias

AllowedChoices: TypeAlias = tuple[str, ...]
Payload: TypeAlias = dict[str, object]
QueryArgs: TypeAlias = list[object]
SqlTuple: TypeAlias = tuple[str, QueryArgs]
