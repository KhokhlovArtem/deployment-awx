# 1. Обновляем систему
sudo apt update && sudo apt upgrade -y

# 2. Устанавливаем Python и необходимые пакеты
sudo apt install -y python3 python3-pip python3-venv git curl

# 3. Устанавливаем Ansible через pip (получаем последнюю версию)
python3 -m pip install --user ansible

# 4. Добавляем Ansible в PATH (добавьте в ~/.bashrc для постоянного использования)
export PATH="$HOME/.local/bin:$PATH"


# 1. Создаем виртуальное окружение для Ansible
python3 -m venv ~/ansible-venv

# 2. Активируем его
source ~/ansible-venv/bin/activate

# 3. Устанавливаем Ansible внутри venv
pip install ansible

# 4. Проверяем установку
ansible --version

# 5. Устанавливаем коллекцию для Kubernetes
ansible-galaxy collection install kubernetes.core

# 6. Теперь запускаем playbook (не забывайте каждый раз активировать venv)
ansible-playbook install-awx-k3s.yml -K

# Чтобы деактивировать venv, когда закончите:
deactivate