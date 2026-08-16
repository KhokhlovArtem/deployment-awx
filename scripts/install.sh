#!/bin/bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and set both passwords." >&2
  exit 1
fi

if [[ ! -x "$HOME/ansible-venv/bin/ansible-playbook" ]]; then
  echo "Ansible venv is missing. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

chmod 600 .env
set -a
# shellcheck disable=SC1091
source .env
set +a

exec "$HOME/ansible-venv/bin/ansible-playbook" playbooks/install.yml "$@"
