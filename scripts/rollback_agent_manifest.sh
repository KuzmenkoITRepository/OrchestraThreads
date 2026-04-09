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

import hashlib
import json
import sys
from pathlib import Path

snapshot = Path(sys.argv[1]).resolve()
manifest = Path(sys.argv[2]).resolve()
payload = manifest.read_bytes()
print(
    json.dumps(
        {
            "ok": True,
            "manifest_path": str(manifest),
            "restored_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "snapshot_path": str(snapshot),
        },
        sort_keys=True,
    )
)
PY
