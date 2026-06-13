# Troubleshooting

## Watch deployment progress
```bash
kubectl get pods -n awx -w
```

## Operator / instance logs
```bash
kubectl logs -n awx deploy/awx-operator-controller-manager
kubectl describe awx awx -n awx
```

## AWX not reachable on NodePort
- Confirm the service: `kubectl get svc -n awx`
- Check the node IP and that `AWX_NODEPORT` (default 30080) is open in the firewall.

## Re-run / update
Idempotent. Change values in `.env`, re-source it, then:
```bash
ansible-playbook playbooks/install.yml -K
```

## Full teardown
```bash
ansible-playbook playbooks/uninstall.yml
```

## ImagePullBackOff on kube-rbac-proxy
The operator's upstream manifest references
`gcr.io/kubebuilder/kube-rbac-proxy`, which is blocked in some regions (GCR).
The kustomization overrides it with a mirror via `images:` (see
`roles/awx/templates/kustomization.yaml.j2`).

Change the mirror in `.env`:
```
KUBE_RBAC_PROXY_IMAGE=quay.io/brancz/kube-rbac-proxy
KUBE_RBAC_PROXY_VERSION=v0.15.0
```
Then re-run the playbook. To clear a stuck operator pod:
```bash
kubectl delete pod -n awx -l control-plane=controller-manager
```

## kubeconfig issues
The playbook copies `/etc/rancher/k3s/k3s.yaml` to `~/.kube/config`.
If `kubectl` fails with connection refused, ensure k3s is running:
```bash
sudo systemctl status k3s
```
