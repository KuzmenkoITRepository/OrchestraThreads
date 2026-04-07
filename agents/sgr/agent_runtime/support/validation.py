from __future__ import annotations


def validate_threads_url(threads_url: str | None) -> None:
    if threads_url is None:
        return
    if threads_url.startswith(("http://", "https://")):
        return
    raise ValueError("threads_url must start with http:// or https://")


def validate_http_endpoint(http_endpoint: str) -> None:
    if not http_endpoint:
        return
    if http_endpoint.startswith(("http://", "https://")):
        return
    raise ValueError("http_endpoint must start with http:// or https://")


def validate_reasoning_steps(max_reasoning_steps: int) -> None:
    if max_reasoning_steps >= 1:
        return
    raise ValueError("max_reasoning_steps must be at least 1")
