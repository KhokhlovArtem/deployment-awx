# AWX Deployment

Deploy [AWX](https://github.com/ansible/awx) on a single VM using **Ansible**, **k3s**, and the **AWX Operator**.

## What it does
1. Installs k3s on the local host.
2. Deploys the AWX Operator via kustomize.
3. Creates secrets (admin + postgres) from `.env`.
4. Applies the AWX custom resource (exposed via NodePort).

## Requirements
- Ubuntu 24.04 LTS x86-64 VM with sudo and Python 3.12 or newer.
- At least 4 vCPU, 8 GB RAM, and 50 GB disk (25 GiB must be free before installation).
- Internet access (k3s + operator pulled from upstream).

## Layout
```
.
├── .env.example           # template for secrets/params (copy to .env)
├── ansible.cfg
├── requirements.txt       # pinned Python dependencies
├── requirements.yml       # Ansible collections
├── inventory/hosts.ini    # localhost, connection=local
├── playbooks/
│   ├── install.yml
│   └── uninstall.yml
├── roles/
│   ├── k3s/               # install k3s + kubeconfig
│   └── awx/               # operator + secret + AWX CR
├── scripts/
│   ├── bootstrap.sh       # apt + venv + ansible + collections
│   ├── install.sh         # load .env and run the install playbook
│   └── uninstall.sh       # load .env and remove AWX
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
cp .env.example .env
chmod 600 .env
$EDITOR .env

# 3. Deploy
scripts/install.sh -K
```

The playbook waits for the operator, database, web and task deployments, and the
AWX API. To inspect the deployment later:
```bash
kubectl get pods -n awx -w
```
AWX will be available at `http://<host-ip>:30080` (login `admin`, password from `.env`).

## Configuration
All settings come from environment variables loaded from `.env` by
`scripts/install.sh` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `K3S_VERSION` | `v1.36.3+k3s1` | exact tested k3s version |
| `AWX_NAMESPACE` | `awx` | target namespace |
| `AWX_OPERATOR_VERSION` | `2.19.1` | AWX Operator version |
| `AWX_NODEPORT` | `30080` | exposed NodePort |
| `AWX_ADMIN_USER` | `admin` | AWX admin user |
| `AWX_ADMIN_PASSWORD` | — (required) | AWX admin password |
| `AWX_POSTGRES_PASSWORD` | — (required) | PostgreSQL password |
| `AWX_RECEPTOR_CA_CERT_PATH` | — | optional trusted local Receptor CA certificate path |
| `AWX_RECEPTOR_CA_KEY_PATH` | — | optional local Receptor CA private key path (mode `0400` or `0600`) |
| `AWX_RECEPTOR_CA_GENERATION` | — | rollout marker required with custom Receptor CA paths |

> `.env` is gitignored. Keep it mode `0600` and never commit real passwords.

> Keep Receptor CA PEM files outside Git. Set all three Receptor CA variables
> together to manage the `awx-receptor-ca` Secret declaratively and roll the
> task pod when the generation value changes.

> The `kubernetes.core.*` modules use the interpreter at `~/ansible-venv/bin/python3`
> (pinned via `ansible_python_interpreter`). Keep `kubernetes` + `PyYAML` in that venv
> (installed by `scripts/bootstrap.sh`).

## Update
Change non-secret settings in `.env`, then re-run `scripts/install.sh -K`. Do not
rotate the PostgreSQL password by editing `.env`; password rotation requires a
separate database-aware procedure.

## Uninstall
```bash
scripts/uninstall.sh
```

This removes the AWX resource and namespace, including namespaced PVCs and
secrets. It does not remove k3s, the virtualenv, or cluster-scoped operator
resources.

See [docs/troubleshooting.md](docs/troubleshooting.md) for more.
