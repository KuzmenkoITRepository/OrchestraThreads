def parse_chat_id(raw: str) -> int:
    stripped = raw.strip()
    if not stripped:
        raise ValueError("TELEGRAM_CHAT_ID_IVAN must be a valid integer chat ID")
    return int(stripped)


def parse_float_env(raw: str | None, key: str) -> float:
    if raw is None or not raw.strip():
        raise ValueError(f"{key} must not be empty")
    return float(raw)


def parse_int_env(raw: str | None, key: str) -> int:
    if raw is None or not raw.strip():
        raise ValueError(f"{key} must not be empty")
    return int(raw)
