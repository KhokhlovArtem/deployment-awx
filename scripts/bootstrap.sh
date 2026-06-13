#!/bin/bash
set -e

echo "=== 1. System packages ==="
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git curl

echo "=== 2. Python venv for Ansible ==="
python3 -m venv ~/ansible-venv
# shellcheck disable=SC1090
source ~/ansible-venv/bin/activate

echo "=== 3. Ansible + Kubernetes Python client ==="
pip install --upgrade pip
pip install ansible kubernetes PyYAML

echo "=== 4. Ansible collections ==="
ansible-galaxy collection install -r requirements.yml

echo ""
echo "=== Bootstrap done ==="
echo "Next:"
echo "  source ~/ansible-venv/bin/activate"
echo "  cp env.example .env   # edit passwords"
echo "  set -a && source .env && set +a"
echo "  ansible-playbook playbooks/install.yml -K"
