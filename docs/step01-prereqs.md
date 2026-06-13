# Host prerequisites

These steps prepare the control host. The recommended path is `scripts/bootstrap.sh`,
which automates everything below. This page documents the manual equivalent.

## Recommended: bootstrap script
```bash
bash scripts/bootstrap.sh
source ~/ansible-venv/bin/activate
```

## Manual setup

### 1. System packages
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl
```

### 2. Python virtualenv for Ansible
```bash
python3 -m venv ~/ansible-venv
source ~/ansible-venv/bin/activate
pip install --upgrade pip
pip install ansible kubernetes PyYAML
ansible --version
```

### 3. Ansible collections
```bash
ansible-galaxy collection install -r requirements.yml
```

### 4. Run the playbook
Always activate the venv first, then export `.env` and run:
```bash
cp env.example .env        # edit passwords
set -a && source .env && set +a
ansible-playbook playbooks/install.yml -K
```

To leave the virtualenv when finished:
```bash
deactivate
```

## Note: Python interpreter for k8s modules
The `kubernetes.core.*` modules run with the **target host interpreter**, not the
venv that runs Ansible. The playbook pins it to `~/ansible-venv/bin/python3`
(via `ansible_python_interpreter` in `playbooks/install.yml`), so `kubernetes`
and `PyYAML` must be installed in that venv — `scripts/bootstrap.sh` does this.
