"""Shared errors for the Orchestra agents lifecycle service."""

from __future__ import annotations


class ManifestValidationError(ValueError):
    """Raised when a manifest cannot be normalized into the service schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = [str(item) for item in errors if str(item).strip()]
        message = "; ".join(self.errors) if self.errors else "manifest validation failed"
        super().__init__(message)


class ServiceError(RuntimeError):
    """HTTP-facing service error with a specific status code."""

    def __init__(self, status: int, message: str) -> None:
        self.status = int(status)
        self.message = str(message)
        super().__init__(self.message)
