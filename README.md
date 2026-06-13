# AWX Deployment

Deploy [AWX](https://github.com/ansible/awx) on a single VM using **Ansible**, **k3s**, and the **AWX Operator**.

## What it does
1. Installs k3s on the local host.
2. Deploys the AWX Operator via kustomize.
3. Creates secrets (admin + postgres) from `.env`.
4. Applies the AWX custom resource (exposed via NodePort).

## Requirements
- Ubuntu/Debian VM with sudo.
- Internet access (k3s + operator pulled from upstream).

## Layout
```
.
├── env.example            # template for secrets/params (copy to .env)
├── ansible.cfg
├── requirements.yml       # Ansible collections
├── inventory/hosts.ini    # localhost, connection=local
├── playbooks/
│   ├── install.yml
│   └── uninstall.yml
├── roles/
│   ├── k3s/               # install k3s + kubeconfig
│   └── awx/               # operator + secret + AWX CR
├── scripts/bootstrap.sh   # apt + venv + ansible + collections
└── docs/
    ├── step01-prereqs.md
    └── troubleshooting.md
```

## Quick start
```bash
git clone <repo> && cd AWX

# 1. Bootstrap host (apt, venv, ansible, collections)
bash scripts/bootstrap.sh
source ~/ansible-venv/bin/activate

# 2. Configure secrets
cp env.example .env
$EDITOR .env
set -a && source .env && set +a   # export vars for the env lookup

# 3. Deploy
ansible-playbook playbooks/install.yml -K
```

Then watch:
```bash
kubectl get pods -n awx -w
```
AWX will be available at `http://<host-ip>:30080` (login `admin`, password from `.env`).

## Configuration
All settings come from environment variables (see `env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `K3S_VERSION` | `stable` | k3s install channel |
| `AWX_NAMESPACE` | `awx` | target namespace |
| `AWX_OPERATOR_VERSION` | `2.19.1` | AWX Operator version |
| `AWX_NODEPORT` | `30080` | exposed NodePort |
| `AWX_ADMIN_USER` | `admin` | AWX admin user |
| `AWX_ADMIN_PASSWORD` | — (required) | AWX admin password |
| `AWX_POSTGRES_PASSWORD` | — (required) | PostgreSQL password |

> `.env` is gitignored. Never commit real passwords.

## Update
Change values in `.env`, re-source it, and re-run `playbooks/install.yml` (idempotent).

## Uninstall
```bash
ansible-playbook playbooks/uninstall.yml
```

See [docs/troubleshooting.md](docs/troubleshooting.md) for more.
