"""Support helpers for backend migration and switch verification."""

from core.orchestra_agents import _migration_manifest as _manifest
from core.orchestra_agents import _migration_switch as _switch
from core.orchestra_agents import _migration_switch_config as _switch_config
from core.orchestra_agents import _migration_types as _types
from core.orchestra_agents import _migration_verify as _verify

ManifestMigrator = _manifest.ManifestMigrator
create_manifest_snapshot = _manifest.create_manifest_snapshot
format_manifest_yaml = _manifest.format_manifest_yaml
load_manifest_payload = _manifest.load_manifest_payload
restore_manifest_snapshot = _manifest.restore_manifest_snapshot

build_controlled_switch_payload = _switch.build_controlled_switch_payload
prepare_backend_switch = _switch.prepare_backend_switch
verify_backend_switch = _switch.verify_backend_switch

DEFAULT_SWITCH_PREPARE_MAX_MS = _switch_config.DEFAULT_SWITCH_PREPARE_MAX_MS
SUPPORTED_SWITCH_BACKENDS = _switch_config.SUPPORTED_SWITCH_BACKENDS

BackendSwitchSummary = _types.BackendSwitchSummary
MigrationCheckSummary = _types.MigrationCheckSummary
RuntimeResolutionSummary = _types.RuntimeResolutionSummary

verify_manifest_migration = _verify.verify_manifest_migration
