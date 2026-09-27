# Развёртывание AWX на удалённой Ubuntu

Схема: **Windows PowerShell → WSL2 Ubuntu → Ansible по SSH → Ubuntu 24.04+ x86_64 → k3s → AWX Operator → AWX**.
Установка выполняется на удалённой машине, а WSL служит контроллером. Вход SSH — **только по ключу**.
Реальное развёртывание и совместимость закреплённых версий ещё требуют проверки: [TODO.md](TODO.md).

## Требования

- Windows с уже настроенной WSL2 и дистрибутивом Ubuntu 24.04+; PowerShell 5.1 или 7+.
- В WSL: Python 3.12+, модуль `venv`, pip, OpenSSH client, Git, CA-сертификаты.
  Системные зависимости устанавливает оператор отдельно; bootstrap не запускает `apt` на контроллере.
- Чистая удалённая Ubuntu 24.04+ x86_64 с работающим SSH, установленным публичным ключом
  и пользователем с sudo либо root. Python на сервере предварительно не требуется.
- Сервер: минимум 4 vCPU, рекомендуется 8 GB RAM и диск 50 GB;
  проверяется не менее 7000 MiB доступной ОС общей RAM и 25 GiB свободного места на `/` перед первой установкой k3s.
- WSL нужен доступ к PyPI и Ansible Galaxy; серверу — к Ubuntu APT, PyPI,
  get.k3s.io, GitHub и реестрам образов (включая Quay и Docker Hub).
- SSH-порт сервера доступен из WSL. NodePort (по умолчанию 30080) доступен из WSL и Windows
  по доверенной частной сети. HTTP без TLS допустим только в такой сети.
  Скрипты не меняют firewall, NAT или TLS и не публикуют сервис в Интернет.

## 1. Подготовить WSL и доверие SSH

Работайте из каталога репозитория в WSL (например, `/mnt/c/Users/.../deployment-AWX`).
Для проекта на Windows-диске права файлов зависят от настроек DrvFS; приватный ключ лучше хранить
в Linux home WSL с правами `0600`. Скрипты не читают и не копируют приватный ключ.

Если ключ защищён passphrase, предварительно загрузите его в SSH-agent **в WSL**:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

При первом подключении вручную сравните показанный fingerprint с отпечатком,
полученным от администратора сервера через доверенный канал, и только затем подтвердите:

```bash
ssh -F /dev/null -o StrictHostKeyChecking=ask \
  -o PreferredAuthentications=publickey -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no -o IdentitiesOnly=yes \
  -i ~/.ssh/id_ed25519 -p 22 ubuntu@192.0.2.10 true
```

Это создаёт запись в `~/.ssh/known_hosts` WSL. Для нестандартного порта доверие привязано
к `[host]:port`. Автоматического доверия новым ключам нет. Launcher использует
`StrictHostKeyChecking=yes`, `BatchMode=yes` и отключает SSH password/keyboard-interactive.
Пользовательские настройки `~/.ssh/config` игнорируются (`-F /dev/null`): адрес и порт передавайте явно.

Agent из интерактивной WSL-сессии не обязательно доступен процессу, запущенному из PowerShell.
Для passphrase-ключа удобнее запускать установку из той WSL-сессии, где доступен `SSH_AUTH_SOCK`.
Для запуска из PowerShell agent должен быть доступен дочернему WSL-процессу; Windows-agent
не подключается автоматически. Незашифрованный ключ можно явно указать через `-Identity`.

## 2. Один раз подготовить контроллер

Из PowerShell в корне репозитория:

```powershell
.\scripts\Deploy-Awx.ps1 -Mode bootstrap -Distribution Ubuntu
```

Имя дистрибутива передавайте точно как в `wsl --list --quiet`, например `Ubuntu-24.04`;
тот же `-Distribution` используйте при установке и удалении.

Либо непосредственно в WSL:

```bash
bash scripts/bootstrap.sh
```

Создаются только проектные `.venv/`, `.ansible/collections/` и `temp/`.
Устанавливаются закреплённые зависимости из `requirements.txt` и `requirements.yml`;
системный Python и глобальные Python-пакеты не изменяются. Повторите bootstrap после изменения зависимостей.
Существующие symlink-каталоги для runtime-путей отвергаются; `temp/` должен оставаться внутри проекта.

## 3. Установить AWX

Из PowerShell (параметр `-Identity` — абсолютный **Linux-путь в WSL**, не Windows-путь):

```powershell
.\scripts\Deploy-Awx.ps1 -TargetHost 192.0.2.10 -User ubuntu `
  -Identity /home/operator/.ssh/id_ed25519 -AskBecomePass
```

Либо из WSL с ранее разблокированным ключом в agent:

```bash
bash scripts/install.sh --host 192.0.2.10 --user ubuntu --ask-become-pass
```

Эквивалент прямого запуска:

```bash
.venv/bin/python scripts/controller.py install --host 192.0.2.10 --user ubuntu -K
```

`-AskBecomePass` / `--ask-become-pass` / `-K` запрашивает пароль **sudo**, не SSH.
При passwordless sudo или входе root этот флаг не нужен. Все удалённые задачи выполняются с become.

Два пароля `AWX_ADMIN_PASSWORD` и `AWX_POSTGRES_PASSWORD` вводятся скрыто, если отсутствуют
в окружении процесса WSL. Минимум 16 символов, примерные значения запрещены.
Для автоматизации настройте эти переменные в окружении WSL через свой менеджер секретов.
Windows-переменные не пересылаются автоматически. Не передавайте пароли в аргументах команд.
В неинтерактивном режиме отсутствие переменной завершает запуск ошибкой.
`.env` и `.env.example` не используются и не загружаются; старые инструкции по ним больше не применяются.
Секреты не записываются во временный инвентарь, файлы контроллера или вывод задач.

На сервере сначала проверяются ОС/архитектура, при необходимости устанавливается Python,
затем проверяются ресурсы и создаётся `/opt/awx-deploy-venv` с закреплёнными Kubernetes/PyYAML.
k3s устанавливается только при отсутствии `/usr/local/bin/k3s`. Затем применяются Operator,
секреты и AWX. Kustomize выполняется на сервере, где находятся отрендеренные файлы.

### Параметры

| PowerShell | WSL runner | Значение / смысл |
|---|---|---|
| `-Mode` | первый аргумент | `bootstrap`, `install` (по умолчанию в PS), `uninstall` |
| `-Distribution` | — | `Ubuntu`, имя установленного дистрибутива WSL2 |
| `-TargetHost` | `--host` | обязательный IP или DNS сервера |
| `-User` | `--user` | обязательный Linux SSH-пользователь |
| `-Port` | `--port` | SSH, по умолчанию 22 |
| `-Identity` | `--identity` | абсолютный путь ключа в WSL; без него используется agent/default SSH identities |
| `-Namespace` | `--namespace` | `awx`; используйте тот же namespace при повторе и удалении |
| `-NodePort` | `--nodeport` | 30080, допустимы 30000–32767 |
| `-PublicUrl` | `--public-url` | явный `http(s)://host[:port]` для проверки через существующий NAT/прокси |
| `-AskBecomePass` | `--ask-become-pass`, `-K` | интерактивный пароль sudo |
| `-ConfirmDelete` | `--confirm-delete` | точное имя удаляемого namespace |

`PublicUrl` меняет только адрес итоговой проверки, не конфигурацию сервиса или сети.
URL не может содержать credentials, путь, query или fragment. HTTPS проверяет сертификат.
Произвольные аргументы Ansible, debug/diff и secret extra-vars launcher не принимает.
Прочие прежние переменные настройки из `.env` не поддерживаются launcher:
версии заданы в playbook/defaults, логин — `admin`. Custom Receptor CA этим entry point
явно не поддерживается; при наличии соответствующих трёх переменных окружения запуск отклоняется.

## Результат и повторный запуск

Playbook ожидает готовности k3s, Operator, AWX, PostgreSQL, web/task deployments и API.
Затем runner проверяет `/api/v2/ping/` **из WSL**: нужен HTTP 200 и JSON с полями
`version`, `instances`, `instance_groups`, а не произвольная HTML-страница.
Выводится URL и логин `admin`. Ненулевой код означает ошибку, в том числе если кластер
уже развёрнут, но итоговая сетевая проверка не прошла.

**Доступность из Windows и браузера автоматически не проверяется.** Откройте выведенный URL
в браузере Windows отдельно. Кластерный kubeconfig остаётся на сервере:
`/etc/rancher/k3s/k3s.yaml` и `~/.kube/config` пользователя become (обычно `/root`), права `0600`.
Файлы сборки находятся в `~/awx-install` того же удалённого пользователя.

При повторе укажите прежние пароли: несовпадение с существующими Kubernetes Secrets
останавливает обновление паролей. Это не механизм ротации или сброса паролей;
изменение пароля вручную внутри AWX/БД требует отдельной согласованной процедуры.
Повторный запуск не обновляет существующий k3s, даже при изменении `k3s_version`.
Сочетание версий из исходного репозитория сохранено, но интеграционно не подтверждено.

## Хранение, резервные копии и удаление

Одноузловой k3s использует локальное хранилище `local-path`: данные привязаны к диску узла,
нет HA, автоматической репликации или настроенного резервного копирования.
Перед эксплуатацией организуйте и проверьте восстановление AWX/PostgreSQL,
секретов и конфигурации по процедурам соответствующей версии Operator.

Удаление требует явного подтверждения namespace:

```powershell
.\scripts\Deploy-Awx.ps1 -Mode uninstall -TargetHost 192.0.2.10 -User ubuntu `
  -Namespace awx -ConfirmDelete awx -AskBecomePass
```

```bash
bash scripts/uninstall.sh --host 192.0.2.10 --user ubuntu \
  --namespace awx --confirm-delete awx -K
```

Удаляются AWX и namespace вместе с Secrets и PVC; локальные PV с reclaim policy Delete
могут потерять данные. Это необратимо без резервной копии. Пароли AWX для удаления не нужны.
k3s, remote venv, kubeconfig, файлы сборки и cluster-scoped ресурсы Operator остаются.
Uninstall рассчитан на сервер с подготовленным `/opt/awx-deploy-venv`.

## Локальные проверки

Offline-тесты не выполняют SSH и не разворачивают AWX:

```bash
mkdir -p temp  # только обычный каталог внутри репозитория
TMP="$PWD/temp" TEMP="$PWD/temp" TMPDIR="$PWD/temp" python3 -B tests/test_controller.py
for script in scripts/bootstrap.sh scripts/install.sh scripts/uninstall.sh; do bash -n "$script"; done
git diff --check
```

Список выполненных и ожидающих проверок: [TODO.md](TODO.md).
Диагностика: [docs/troubleshooting.md](docs/troubleshooting.md).
