#!/bin/bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$repo_root"
exec "$repo_root/.venv/bin/python" "$repo_root/scripts/controller.py" install "$@"
