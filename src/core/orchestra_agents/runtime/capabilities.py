"""Backend capability registry for Orchestra agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendCapabilities:
    """Declares which capability-gated features a backend supports."""

    supports_session_routing: bool
    supports_thread_filtered_stop: bool
    supports_duplicate_detection: bool
    supports_mcp_lifecycle: bool


class BackendRegistry:
    """Maps backend type strings to their declared capabilities."""

    def __init__(self) -> None:
        self._backends: dict[str, BackendCapabilities] = {}

    def register(
        self,
        backend_type: str,
        capabilities: BackendCapabilities,
    ) -> None:
        """Register capabilities for a backend type."""
        self._backends[backend_type] = capabilities

    def available_backends(self) -> frozenset[str]:
        """Return all registered backend type names."""
        return frozenset(self._backends)

    def get_capabilities(self, backend_type: str) -> BackendCapabilities:
        """Look up capabilities for a registered backend type."""
        try:
            return self._backends[backend_type]
        except KeyError:
            raise ValueError(backend_type) from None

    def supports(self, backend_type: str, capability: str) -> bool:
        """Check whether a backend supports a named capability."""
        caps = self.get_capabilities(backend_type)
        return bool(getattr(caps, capability))


def _build_default_registry() -> BackendRegistry:
    """Populate registry with known backend capabilities."""
    reg = BackendRegistry()
    reg.register(
        "sgr_minimax",
        BackendCapabilities(
            supports_session_routing=True,
            supports_thread_filtered_stop=False,
            supports_duplicate_detection=False,
            supports_mcp_lifecycle=True,
        ),
    )
    reg.register(
        "agent_mux",
        BackendCapabilities(
            supports_session_routing=False,
            supports_thread_filtered_stop=True,
            supports_duplicate_detection=True,
            supports_mcp_lifecycle=True,
        ),
    )
    reg.register(
        "opencode_omo",
        BackendCapabilities(
            supports_session_routing=False,
            supports_thread_filtered_stop=True,
            supports_duplicate_detection=True,
            supports_mcp_lifecycle=True,
        ),
    )
    return reg


registry: BackendRegistry = _build_default_registry()
