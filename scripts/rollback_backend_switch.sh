#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  >&2 printf 'usage: %s <snapshot-path> <manifest-path>\n' "$0"
  exit 64
fi

snapshot_path="$1"
manifest_path="$2"
python_bin="${PYTHON_BIN:-.venv/bin/python}"

if [ ! -f "$snapshot_path" ]; then
  >&2 printf 'snapshot not found: %s\n' "$snapshot_path"
  exit 66
fi

mkdir -p "$(dirname "$manifest_path")"
cp "$snapshot_path" "$manifest_path"

"$python_bin" - "$snapshot_path" "$manifest_path" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

snapshot = Path(sys.argv[1]).resolve()
manifest = Path(sys.argv[2]).resolve()
loaded = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
backend = loaded.get("backend") or {}
print(
    json.dumps(
        {
            "ok": True,
            "clean_state_only": True,
            "manifest_path": str(manifest),
            "restart_required": True,
            "restored_backend_type": str(backend.get("type") or ""),
            "snapshot_path": str(snapshot),
        },
        sort_keys=True,
    )
)
PY
