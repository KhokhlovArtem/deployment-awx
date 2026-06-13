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

## kubeconfig issues
The playbook copies `/etc/rancher/k3s/k3s.yaml` to `~/.kube/config`.
If `kubectl` fails with connection refused, ensure k3s is running:
```bash
sudo systemctl status k3s
```
