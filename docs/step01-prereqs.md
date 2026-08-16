# Host prerequisites

These steps prepare the control host. The recommended path is `scripts/bootstrap.sh`,
which automates everything below. This page documents the manual equivalent.

## Recommended: bootstrap script
```bash
bash scripts/bootstrap.sh
source ~/ansible-venv/bin/activate
```

The host must be Ubuntu 24.04 LTS x86-64 with Python 3.12 or newer, at least
4 vCPU, 8 GB RAM, a 50 GB disk, and 25 GiB free on `/`. The playbook checks
these values before installing k3s.

## Manual setup

### 1. System packages
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates python3 python3-pip python3-venv git curl
```

### 2. Python virtualenv for Ansible
```bash
python3 -m venv ~/ansible-venv
source ~/ansible-venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ansible --version
```

### 3. Ansible collections
```bash
ansible-galaxy collection install -r requirements.yml
```

### 4. Run the playbook
Create `.env`, then use the install wrapper to load it and run Ansible with a
UTF-8 locale:
```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
scripts/install.sh -K
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
