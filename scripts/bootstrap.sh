#!/bin/bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

echo "=== 1. System packages ==="
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl git python3 python3-pip python3-venv

python3 -c 'import sys; sys.exit("Python 3.12 or newer is required") if sys.version_info < (3, 12) else None'

echo "=== 2. Python venv for Ansible ==="
python3 -m venv ~/ansible-venv
# shellcheck disable=SC1090
source ~/ansible-venv/bin/activate

echo "=== 3. Ansible + Kubernetes Python client ==="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "=== 4. Ansible collections ==="
ansible-galaxy collection install -r requirements.yml

echo ""
echo "=== Bootstrap done ==="
echo "Next:"
echo "  source ~/ansible-venv/bin/activate"
echo "  cp .env.example .env   # edit passwords"
echo "  scripts/install.sh -K"
