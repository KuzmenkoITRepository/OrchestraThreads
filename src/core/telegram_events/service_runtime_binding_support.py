"""Compatibility wrapper for telegram runtime binding helpers."""

from core.telegram_events.runtime_binding_support import (
    apply_runtime_resources as apply_runtime_resources,
)
from core.telegram_events.runtime_binding_support import (
    extract_thread_id as extract_thread_id,
)
from core.telegram_events.runtime_binding_support import (
    register_with_threads as register_with_threads,
)
from core.telegram_events.runtime_binding_support import (
    registration_base_url as registration_base_url,
)
from core.telegram_events.runtime_binding_support import (
    require_threads_client as require_threads_client,
)
from core.telegram_events.runtime_binding_support import (
    runtime_resource_config as runtime_resource_config,
)
