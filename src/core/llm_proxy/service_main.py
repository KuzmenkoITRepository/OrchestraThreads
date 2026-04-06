from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Final

from aiohttp import web

from core.llm_proxy.client_config import parse_csv
from core.llm_proxy.codex_oauth import resolve_default_auth_profiles_path
from core.llm_proxy.service import (
    DEFAULT_ACCOUNT_FAILURE_COOLDOWN_SECONDS,
    DEFAULT_BASE_URL,
    DEFAULT_FALLBACK_TIMEOUT_SECONDS,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_INSTRUCTIONS,
    LLMProxyService,
    ProxyConfig,
    build_app,
)

DEFAULT_HOST: Final[str] = "0.0.0.0"
DEFAULT_PORT: Final[int] = 8787
DEFAULT_TIMEOUT_SECONDS: Final[str] = "180"


def _first_nonempty(*values: str | None) -> str:
    for value in values:
        if value:
            stripped = value.strip()
            if stripped:
                return stripped
    return ""


def _env(*names: str) -> str:
    return _first_nonempty(*(os.getenv(name) for name in names))


def _coerce_int(raw: str, default: int) -> int:
    cleaned = raw.strip()
    return int(cleaned) if cleaned else default


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _coerce_bool(value: object, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def _add_common_network_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port.")


def _add_codex_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        default=_env(
            "LLM_PROXY_CODEX_MODEL",
            "ORCHESTRA_CORE_CODEX_MODEL",
            "MAIN_AGENT_CODEX_MODEL",
            "CODEX_MODEL",
        )
        or DEFAULT_MODEL,
        help="Managed Codex model id.",
    )
    parser.add_argument(
        "--base-url",
        default=_env(
            "LLM_PROXY_CODEX_UPSTREAM_BASE_URL",
            "ORCHESTRA_CORE_CODEX_UPSTREAM_BASE_URL",
            "MAIN_AGENT_CODEX_UPSTREAM_BASE_URL",
            "CODEX_BASE_URL",
        )
        or DEFAULT_BASE_URL,
        help="Codex base URL before /codex/responses is appended.",
    )
    parser.add_argument(
        "--auth-profiles-path",
        default=_env("LLM_PROXY_AUTH_PROFILES_PATH", "CODEX_AUTH_PROFILES_PATH")
        or str(resolve_default_auth_profiles_path()),
        help="Path to shared OpenClaw auth-profiles.json.",
    )
    parser.add_argument(
        "--profile-id",
        default=_env(
            "LLM_PROXY_CODEX_PRIMARY_PROFILE_ID",
            "ORCHESTRA_CORE_CODEX_PRIMARY_PROFILE_ID",
            "MAIN_AGENT_CODEX_PRIMARY_PROFILE_ID",
            "CODEX_OAUTH_PROFILE_ID",
        ),
        help="Primary OpenClaw profile id.",
    )
    parser.add_argument(
        "--profile-ids",
        default=_env(
            "LLM_PROXY_CODEX_PROFILE_IDS",
            "LLM_ROUTER_CODEX_PROFILE_IDS",
            "ORCHESTRA_CORE_CODEX_PROXY_PROFILE_IDS",
            "MAIN_AGENT_CODEX_PROXY_PROFILE_IDS",
            "CODEX_OAUTH_PROFILE_IDS",
        ),
        help="Optional comma-separated Codex profile ids for explicit rotation order.",
    )


def _add_prompt_and_sampling_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--default-system-instructions",
        default=os.getenv("LLM_PROXY_DEFAULT_SYSTEM_INSTRUCTIONS", DEFAULT_SYSTEM_INSTRUCTIONS),
        help="Fallback system instructions for OpenAI-compatible requests.",
    )
    parser.add_argument(
        "--text-verbosity",
        default=_env(
            "LLM_PROXY_CODEX_TEXT_VERBOSITY",
            "ORCHESTRA_CORE_CODEX_TEXT_VERBOSITY",
            "MAIN_AGENT_CODEX_TEXT_VERBOSITY",
            "CODEX_FRAMEWORK_TEXT_VERBOSITY",
        )
        or "medium",
        help="Codex text verbosity.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=_env(
            "LLM_PROXY_CODEX_REASONING_EFFORT",
            "ORCHESTRA_CORE_CODEX_REASONING_EFFORT",
            "MAIN_AGENT_CODEX_REASONING_EFFORT",
            "CODEX_FRAMEWORK_REASONING_EFFORT",
        ),
        help="Optional Codex reasoning effort.",
    )
    parser.add_argument(
        "--reasoning-summary",
        default=_env(
            "LLM_PROXY_CODEX_REASONING_SUMMARY",
            "ORCHESTRA_CORE_CODEX_REASONING_SUMMARY",
            "MAIN_AGENT_CODEX_REASONING_SUMMARY",
            "CODEX_FRAMEWORK_REASONING_SUMMARY",
        )
        or "auto",
        help="Codex reasoning summary mode.",
    )
    parser.add_argument(
        "--temperature",
        default=_env(
            "LLM_PROXY_CODEX_TEMPERATURE",
            "ORCHESTRA_CORE_CODEX_TEMPERATURE",
            "MAIN_AGENT_CODEX_TEMPERATURE",
            "CODEX_FRAMEWORK_TEMPERATURE",
        ),
        help="Optional default temperature.",
    )


def _add_timeout_and_state_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=_coerce_int(
            _env(
                "LLM_PROXY_CODEX_REQUEST_TIMEOUT",
                "ORCHESTRA_CORE_CODEX_REQUEST_TIMEOUT",
                "MAIN_AGENT_CODEX_REQUEST_TIMEOUT",
                "CODEX_FRAMEWORK_REQUEST_TIMEOUT",
            )
            or DEFAULT_TIMEOUT_SECONDS,
            int(DEFAULT_TIMEOUT_SECONDS),
        ),
        help="Upstream Codex request timeout.",
    )
    parser.add_argument(
        "--account-failure-cooldown-seconds",
        type=int,
        default=_coerce_int(
            _env(
                "LLM_PROXY_ACCOUNT_FAILURE_COOLDOWN_SECONDS",
                "LLM_ROUTER_ACCOUNT_FAILURE_COOLDOWN_SECONDS",
                "ORCHESTRA_CORE_CODEX_ACCOUNT_FAILURE_COOLDOWN_SECONDS",
                "MAIN_AGENT_CODEX_ACCOUNT_FAILURE_COOLDOWN_SECONDS",
            )
            or str(DEFAULT_ACCOUNT_FAILURE_COOLDOWN_SECONDS),
            DEFAULT_ACCOUNT_FAILURE_COOLDOWN_SECONDS,
        ),
        help="Seconds to keep a failed Codex account on cooldown before retrying it.",
    )
    parser.add_argument(
        "--rotation-state-path",
        default=_env(
            "LLM_PROXY_STATE_PATH",
            "LLM_ROUTER_STATE_PATH",
            "ORCHESTRA_CORE_CODEX_PROXY_STATE_PATH",
            "MAIN_AGENT_CODEX_PROXY_STATE_PATH",
        ),
        help="Path to persisted llm_proxy runtime state.",
    )


def _add_fallback_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fallback-base-url",
        default=_env(
            "LLM_PROXY_FALLBACK_OPENAI_API_BASE_URL",
            "LLM_ROUTER_OPENAI_COMPAT_API_BASE_URL",
            "ORCHESTRA_CORE_OPENAI_COMPAT_API_BASE_URL",
            "MAIN_AGENT_OPENAI_COMPAT_API_BASE_URL",
            "OPENAI_API_BASE_URL",
        ),
        help="Optional OpenAI-compatible fallback base URL.",
    )
    parser.add_argument(
        "--fallback-api-key",
        default=_env(
            "LLM_PROXY_FALLBACK_OPENAI_API_KEY",
            "LLM_ROUTER_OPENAI_COMPAT_API_KEY",
            "ORCHESTRA_CORE_OPENAI_COMPAT_API_KEY",
            "MAIN_AGENT_OPENAI_COMPAT_API_KEY",
            "OPENAI_API_KEY",
        ),
        help="Optional OpenAI-compatible fallback API key.",
    )
    parser.add_argument(
        "--fallback-model",
        default=_env(
            "LLM_PROXY_FALLBACK_OPENAI_MODEL",
            "LLM_ROUTER_OPENAI_COMPAT_MODEL",
            "ORCHESTRA_CORE_OPENAI_COMPAT_MODEL",
            "MAIN_AGENT_OPENAI_COMPAT_MODEL",
            "OPENAI_MODEL",
        ),
        help="Optional fallback model id used when all Codex accounts are unavailable.",
    )
    parser.add_argument(
        "--fallback-timeout-seconds",
        type=int,
        default=_coerce_int(
            _env(
                "LLM_PROXY_FALLBACK_OPENAI_TIMEOUT",
                "LLM_ROUTER_OPENAI_COMPAT_TIMEOUT",
                "ORCHESTRA_CORE_OPENAI_COMPAT_TIMEOUT",
                "MAIN_AGENT_OPENAI_COMPAT_TIMEOUT",
                "OPENAI_API_TIMEOUT",
            )
            or str(DEFAULT_FALLBACK_TIMEOUT_SECONDS),
            DEFAULT_FALLBACK_TIMEOUT_SECONDS,
        ),
        help="Fallback OpenAI-compatible request timeout.",
    )


def _add_langfuse_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--langfuse-enabled",
        default=os.getenv("LLM_PROXY_LANGFUSE_ENABLED", "0"),
        help="Enable Langfuse tracing inside llm_proxy.",
    )
    parser.add_argument(
        "--langfuse-public-key",
        default=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        help="Langfuse public key.",
    )
    parser.add_argument(
        "--langfuse-secret-key",
        default=os.getenv("LANGFUSE_SECRET_KEY", ""),
        help="Langfuse secret key.",
    )
    parser.add_argument(
        "--langfuse-base-url",
        default=_env("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
        help="Langfuse base URL.",
    )
    parser.add_argument(
        "--langfuse-environment",
        default=_env("LLM_PROXY_LANGFUSE_ENVIRONMENT", "LANGFUSE_TRACING_ENVIRONMENT"),
        help="Optional Langfuse environment label.",
    )
    parser.add_argument(
        "--langfuse-release",
        default=os.getenv("LLM_PROXY_LANGFUSE_RELEASE", ""),
        help="Optional Langfuse release/version label.",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Universal llm_proxy service.")
    _add_common_network_args(parser)
    _add_codex_args(parser)
    _add_prompt_and_sampling_args(parser)
    _add_timeout_and_state_args(parser)
    _add_fallback_args(parser)
    _add_langfuse_args(parser)
    return parser


def _resolve_rotation_state_path(args: argparse.Namespace, auth_profiles_path: Path) -> Path:
    path_value = str(args.rotation_state_path).strip()
    if path_value:
        return Path(path_value).expanduser()
    return auth_profiles_path.parent / "proxy-state.json"


def _resolve_temperature(raw_temperature: object) -> float | None:
    normalized = str(raw_temperature).strip()
    if not normalized:
        return None
    return float(normalized)


def build_config_from_args(args: argparse.Namespace) -> ProxyConfig:
    temperature = _resolve_temperature(args.temperature)
    auth_profiles_path = Path(args.auth_profiles_path).expanduser()
    rotation_state_path = _resolve_rotation_state_path(args, auth_profiles_path)
    return ProxyConfig(
        host=args.host,
        port=args.port,
        model=args.model,
        base_url=args.base_url,
        auth_profiles_path=auth_profiles_path,
        profile_id=args.profile_id.strip() or None,
        profile_ids=parse_csv(args.profile_ids),
        default_system_instructions=args.default_system_instructions,
        text_verbosity=args.text_verbosity.strip() or "medium",
        reasoning_effort=args.reasoning_effort.strip() or None,
        reasoning_summary=args.reasoning_summary.strip() or "auto",
        temperature=temperature,
        request_timeout_seconds=args.request_timeout_seconds,
        account_failure_cooldown_seconds=max(1, args.account_failure_cooldown_seconds),
        rotation_state_path=rotation_state_path,
        fallback_base_url=args.fallback_base_url.strip() or None,
        fallback_api_key=args.fallback_api_key.strip() or None,
        fallback_model=args.fallback_model.strip() or None,
        fallback_timeout_seconds=max(1, args.fallback_timeout_seconds),
        langfuse_enabled=_coerce_bool(args.langfuse_enabled, False),
        langfuse_public_key=args.langfuse_public_key.strip() or None,
        langfuse_secret_key=args.langfuse_secret_key.strip() or None,
        langfuse_base_url=args.langfuse_base_url.strip() or None,
        langfuse_environment=args.langfuse_environment.strip() or None,
        langfuse_release=args.langfuse_release.strip() or None,
    )


def _build_startup_log_payload(config: ProxyConfig, service: LLMProxyService) -> dict[str, object]:
    return {
        "status": "listening",
        "listen": f"http://{config.host}:{config.port}",
        "openai_base_url": f"http://{config.host}:{config.port}/v1",
        "codex_base_url": f"http://{config.host}:{config.port}/v1/codex/responses",
        "managed_model": config.model,
        "auth_profiles_path": str(config.auth_profiles_path),
        "profile_id": config.profile_id,
        "profile_ids": list(config.profile_ids),
        "codex_upstream_base_url": config.base_url,
        "rotation_state_path": str(config.rotation_state_path),
        "fallback_enabled": service.router.fallback_transport.enabled,
        "fallback_model": str(getattr(service.router.fallback_transport, "model", "")).strip()
        or None,
        "langfuse_enabled": service.telemetry.enabled,
        "langfuse_base_url": config.langfuse_base_url,
    }


def _log_startup(config: ProxyConfig, service: LLMProxyService) -> None:
    payload = _build_startup_log_payload(config, service)
    message = json.dumps(payload, ensure_ascii=False)
    logging.getLogger(__name__).info(message)


async def _run(config: ProxyConfig) -> None:
    service = LLMProxyService(config)
    app = build_app(service)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=config.host, port=config.port)
    await site.start()
    _log_startup(config, service)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        await runner.cleanup()
        raise
    await runner.cleanup()


def main() -> int:
    configure_logging()
    args = build_arg_parser().parse_args()
    config = build_config_from_args(args)
    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
