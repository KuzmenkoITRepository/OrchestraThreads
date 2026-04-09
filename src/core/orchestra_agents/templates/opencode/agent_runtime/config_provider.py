"""Temporary compatibility shim for Task 7.5; delete in Task 8."""

from __future__ import annotations

from core.orchestra_agents.backends.opencode import config_provider as _provider

_CONTEXT_LIMIT = _provider._CONTEXT_LIMIT
_DEFAULT_OMNIROUTE_URL = _provider._DEFAULT_OMNIROUTE_URL
_OUTPUT_LIMIT = _provider._OUTPUT_LIMIT
ProviderModel = _provider.ProviderModel
ProviderModelMap = _provider.ProviderModelMap
_extend_names = _provider._extend_names
_model_entry = _provider._model_entry
_model_map = _provider._model_map
_model_name = _provider._model_name
_provider_models = _provider._provider_models
_provider_options = _provider._provider_options
build_provider_entry = _provider.build_provider_entry
