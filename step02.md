cat > ~/install-awx-complete.sh << 'EOF'
#!/bin/bash
set -e

echo "=== 1. Установка k3s (если не установлен) ==="
if ! command -v kubectl &> /dev/null; then
    curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
    sudo chmod 644 /etc/rancher/k3s/k3s.yaml
    mkdir -p ~/.kube
    sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
    sudo chown $USER:$USER ~/.kube/config
fi

echo "=== 2. Ожидание готовности k3s ==="
kubectl get nodes

echo "=== 3. Установка AWX Operator через kustomize ==="
mkdir -p ~/awx-install
cd ~/awx-install

cat << 'KUSTOMIZATION' > kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: awx
resources:
  - github.com/ansible/awx-operator/config/default?ref=2.19.1
images:
  - name: quay.io/ansible/awx-operator
    newTag: 2.19.1
KUSTOMIZATION

kubectl apply -k .

echo "=== 4. Ожидание запуска оператора ==="
sleep 10
kubectl wait --for=condition=ready pod -l control-plane=controller-manager -n awx --timeout=120s || true

echo "=== 5. Создание секретов AWX ==="
kubectl create namespace awx 2>/dev/null || true

kubectl -n awx create secret generic awx-secret \
  --from-literal=admin_password='YourStrongPass123!' \
  --from-literal=postgres_password='YourDBStrongPass456!' \
  --dry-run=client -o yaml | kubectl apply -f -

echo "=== 6. Деплой AWX ==="
cat << 'AWXCR' | kubectl apply -f -
apiVersion: awx.ansible.com/v1beta1
kind: AWX
metadata:
  name: awx
  namespace: awx
spec:
  service_type: nodeport
  nodeport_port: 30080
  admin_user: admin
  admin_password_secret: awx-secret
  postgres_configuration_secret: awx-secret
AWXCR

echo "=== 7. Ожидание запуска AWX (~5-10 минут) ==="
echo "Следите за статусом: kubectl get pods -n awx -w"

# Добавляем в /etc/hosts если нужно
if ! grep -q "awx.local" /etc/hosts; then
    echo "127.0.0.1 awx.local" | sudo tee -a /etc/hosts
fi

echo ""
echo "=== Установка запущена! ==="
echo "Проверьте статус: kubectl get pods -n awx"
echo "URL: https://awx.local:30080"
echo "Login: admin"
echo "Password: YourStrongPass123!"
EOF

chmod +x ~/install-awx-complete.sh
./install-awx-complete.sh