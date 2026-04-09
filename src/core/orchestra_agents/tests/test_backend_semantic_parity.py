"""Cross-backend semantic parity tests for the unified contract.

Tests invariant behaviors from unified_backend_semantics.md.
Initially RED for current backend divergences — this is correct TDD state.
"""

from __future__ import annotations

import unittest

from core.orchestra_agents.tests._parity_bases import DeliveryBase, LifecycleBase


class SgrLifecycle(LifecycleBase):
    """SGR lifecycle invariants."""

    backend_type = "sgr_minimax"


class SgrDelivery(DeliveryBase):
    """SGR delivery invariants."""

    backend_type = "sgr_minimax"


class MuxLifecycle(LifecycleBase):
    """Mux lifecycle invariants."""

    backend_type = "agent_mux"


class MuxDelivery(DeliveryBase):
    """Mux delivery invariants."""

    backend_type = "agent_mux"


class OcLifecycle(LifecycleBase):
    """Opencode lifecycle invariants."""

    backend_type = "opencode_omo"


class OcDelivery(DeliveryBase):
    """Opencode delivery invariants."""

    backend_type = "opencode_omo"


if __name__ == "__main__":
    unittest.main()
