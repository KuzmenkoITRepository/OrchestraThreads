from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web

from .client_config import parse_csv
from .codex_oauth import resolve_default_auth_profiles_path
from .service import (
    DEFAULT_ACCOUNT_FAILURE_COOLDOWN_SECONDS,
    DEFAULT_BASE_URL,
    DEFAULT_FALLBACK_TIMEOUT_SECONDS,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_INSTRUCTIONS,
    LLMProxyService,
    ProxyConfig,
    build_app,
)


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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Universal llm_proxy service.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host.")
    parser.add_argument("--port", type=int, default=8787, help="Bind port.")
    parser.add_argument(
        "--model",
        default=(
            os.getenv("LLM_PROXY_CODEX_MODEL")
            or os.getenv("ORCHESTRA_CORE_CODEX_MODEL")
            or os.getenv("MAIN_AGENT_CODEX_MODEL")
            or os.getenv("CODEX_MODEL", DEFAULT_MODEL)
        ),
        help="Managed Codex model id.",
    )
    parser.add_argument(
        "--base-url",
        default=(
            os.getenv("LLM_PROXY_CODEX_UPSTREAM_BASE_URL")
            or os.getenv("ORCHESTRA_CORE_CODEX_UPSTREAM_BASE_URL")
            or os.getenv("MAIN_AGENT_CODEX_UPSTREAM_BASE_URL")
            or os.getenv("CODEX_BASE_URL", DEFAULT_BASE_URL)
        ),
        help="Codex base URL before /codex/responses is appended.",
    )
    parser.add_argument(
        "--auth-profiles-path",
        default=(
            os.getenv("LLM_PROXY_AUTH_PROFILES_PATH")
            or os.getenv("CODEX_AUTH_PROFILES_PATH")
            or str(resolve_default_auth_profiles_path())
        ),
        help="Path to shared OpenClaw auth-profiles.json.",
    )
    parser.add_argument(
        "--profile-id",
        default=(
            os.getenv("LLM_PROXY_CODEX_PRIMARY_PROFILE_ID")
            or os.getenv("ORCHESTRA_CORE_CODEX_PRIMARY_PROFILE_ID")
            or os.getenv("MAIN_AGENT_CODEX_PRIMARY_PROFILE_ID")
            or os.getenv("CODEX_OAUTH_PROFILE_ID", "")
        ),
        help="Primary OpenClaw profile id.",
    )
    parser.add_argument(
        "--profile-ids",
        default=(
            os.getenv("LLM_PROXY_CODEX_PROFILE_IDS")
            or os.getenv("LLM_ROUTER_CODEX_PROFILE_IDS")
            or os.getenv("ORCHESTRA_CORE_CODEX_PROXY_PROFILE_IDS")
            or os.getenv("MAIN_AGENT_CODEX_PROXY_PROFILE_IDS")
            or os.getenv("CODEX_OAUTH_PROFILE_IDS", "")
        ),
        help="Optional comma-separated Codex profile ids for explicit rotation order.",
    )
    parser.add_argument(
        "--default-system-instructions",
        default=os.getenv("LLM_PROXY_DEFAULT_SYSTEM_INSTRUCTIONS", DEFAULT_SYSTEM_INSTRUCTIONS),
        help="Fallback system instructions for OpenAI-compatible requests.",
    )
    parser.add_argument(
        "--text-verbosity",
        default=(
            os.getenv("LLM_PROXY_CODEX_TEXT_VERBOSITY")
            or os.getenv("ORCHESTRA_CORE_CODEX_TEXT_VERBOSITY")
            or os.getenv("MAIN_AGENT_CODEX_TEXT_VERBOSITY")
            or os.getenv("CODEX_FRAMEWORK_TEXT_VERBOSITY", "medium")
        ),
        help="Codex text verbosity.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=(
            os.getenv("LLM_PROXY_CODEX_REASONING_EFFORT")
            or os.getenv("ORCHESTRA_CORE_CODEX_REASONING_EFFORT")
            or os.getenv("MAIN_AGENT_CODEX_REASONING_EFFORT")
            or os.getenv("CODEX_FRAMEWORK_REASONING_EFFORT", "")
        ),
        help="Optional Codex reasoning effort.",
    )
    parser.add_argument(
        "--reasoning-summary",
        default=(
            os.getenv("LLM_PROXY_CODEX_REASONING_SUMMARY")
            or os.getenv("ORCHESTRA_CORE_CODEX_REASONING_SUMMARY")
            or os.getenv("MAIN_AGENT_CODEX_REASONING_SUMMARY")
            or os.getenv("CODEX_FRAMEWORK_REASONING_SUMMARY", "auto")
        ),
        help="Codex reasoning summary mode.",
    )
    parser.add_argument(
        "--temperature",
        default=(
            os.getenv("LLM_PROXY_CODEX_TEMPERATURE")
            or os.getenv("ORCHESTRA_CORE_CODEX_TEMPERATURE")
            or os.getenv("MAIN_AGENT_CODEX_TEMPERATURE")
            or os.getenv("CODEX_FRAMEWORK_TEMPERATURE", "")
        ),
        help="Optional default temperature.",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=int(
            os.getenv("LLM_PROXY_CODEX_REQUEST_TIMEOUT")
            or os.getenv("ORCHESTRA_CORE_CODEX_REQUEST_TIMEOUT")
            or os.getenv("MAIN_AGENT_CODEX_REQUEST_TIMEOUT")
            or os.getenv("CODEX_FRAMEWORK_REQUEST_TIMEOUT", "180")
        ),
        help="Upstream Codex request timeout.",
    )
    parser.add_argument(
        "--account-failure-cooldown-seconds",
        type=int,
        default=int(
            os.getenv("LLM_PROXY_ACCOUNT_FAILURE_COOLDOWN_SECONDS")
            or os.getenv("LLM_ROUTER_ACCOUNT_FAILURE_COOLDOWN_SECONDS")
            or os.getenv("ORCHESTRA_CORE_CODEX_ACCOUNT_FAILURE_COOLDOWN_SECONDS")
            or os.getenv("MAIN_AGENT_CODEX_ACCOUNT_FAILURE_COOLDOWN_SECONDS")
            or str(DEFAULT_ACCOUNT_FAILURE_COOLDOWN_SECONDS)
        ),
        help="Seconds to keep a failed Codex account on cooldown before retrying it.",
    )
    parser.add_argument(
        "--rotation-state-path",
        default=(
            os.getenv("LLM_PROXY_STATE_PATH")
            or os.getenv("LLM_ROUTER_STATE_PATH")
            or os.getenv("ORCHESTRA_CORE_CODEX_PROXY_STATE_PATH")
            or os.getenv("MAIN_AGENT_CODEX_PROXY_STATE_PATH")
            or ""
        ),
        help="Path to persisted llm_proxy runtime state.",
    )
    parser.add_argument(
        "--fallback-base-url",
        default=(
            os.getenv("LLM_PROXY_FALLBACK_OPENAI_API_BASE_URL")
            or os.getenv("LLM_ROUTER_OPENAI_COMPAT_API_BASE_URL")
            or os.getenv("ORCHESTRA_CORE_OPENAI_COMPAT_API_BASE_URL")
            or os.getenv("MAIN_AGENT_OPENAI_COMPAT_API_BASE_URL")
            or os.getenv("OPENAI_API_BASE_URL")
            or ""
        ),
        help="Optional OpenAI-compatible fallback base URL.",
    )
    parser.add_argument(
        "--fallback-api-key",
        default=(
            os.getenv("LLM_PROXY_FALLBACK_OPENAI_API_KEY")
            or os.getenv("LLM_ROUTER_OPENAI_COMPAT_API_KEY")
            or os.getenv("ORCHESTRA_CORE_OPENAI_COMPAT_API_KEY")
            or os.getenv("MAIN_AGENT_OPENAI_COMPAT_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        ),
        help="Optional OpenAI-compatible fallback API key.",
    )
    parser.add_argument(
        "--fallback-model",
        default=(
            os.getenv("LLM_PROXY_FALLBACK_OPENAI_MODEL")
            or os.getenv("LLM_ROUTER_OPENAI_COMPAT_MODEL")
            or os.getenv("ORCHESTRA_CORE_OPENAI_COMPAT_MODEL")
            or os.getenv("MAIN_AGENT_OPENAI_COMPAT_MODEL")
            or os.getenv("OPENAI_MODEL")
            or ""
        ),
        help="Optional fallback model id used when all Codex accounts are unavailable.",
    )
    parser.add_argument(
        "--fallback-timeout-seconds",
        type=int,
        default=int(
            os.getenv("LLM_PROXY_FALLBACK_OPENAI_TIMEOUT")
            or os.getenv("LLM_ROUTER_OPENAI_COMPAT_TIMEOUT")
            or os.getenv("ORCHESTRA_CORE_OPENAI_COMPAT_TIMEOUT")
            or os.getenv("MAIN_AGENT_OPENAI_COMPAT_TIMEOUT")
            or os.getenv("OPENAI_API_TIMEOUT")
            or str(DEFAULT_FALLBACK_TIMEOUT_SECONDS)
        ),
        help="Fallback OpenAI-compatible request timeout.",
    )
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
        default=os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "",
        help="Langfuse base URL.",
    )
    parser.add_argument(
        "--langfuse-environment",
        default=os.getenv("LLM_PROXY_LANGFUSE_ENVIRONMENT") or os.getenv("LANGFUSE_TRACING_ENVIRONMENT") or "",
        help="Optional Langfuse environment label.",
    )
    parser.add_argument(
        "--langfuse-release",
        default=os.getenv("LLM_PROXY_LANGFUSE_RELEASE", ""),
        help="Optional Langfuse release/version label.",
    )
    return parser


def build_config_from_args(args: argparse.Namespace) -> ProxyConfig:
    temperature = float(args.temperature) if str(args.temperature).strip() else None
    auth_profiles_path = Path(args.auth_profiles_path).expanduser()
    rotation_state_path = (
        Path(args.rotation_state_path).expanduser()
        if str(args.rotation_state_path).strip()
        else auth_profiles_path.parent / "proxy-state.json"
    )
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


async def _run(config: ProxyConfig) -> None:
    service = LLMProxyService(config)
    app = build_app(service)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=config.host, port=config.port)
    await site.start()
    logging.getLogger(__name__).info(
        json.dumps(
            {
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
                "fallback_model": service.router.fallback_transport.model or None,
                "langfuse_enabled": service.telemetry.enabled,
                "langfuse_base_url": config.langfuse_base_url,
            },
            ensure_ascii=False,
        )
    )
    try:
        await asyncio.Event().wait()
    finally:
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
    raise SystemExit(main())
