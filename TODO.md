# Постоянный план настройки и проверки

## Реализовано

- [x] PowerShell → WSL runner; прямой запуск из WSL и Bash wrappers.
- [x] Явный удалённый inventory, SSH key only, host key checking, sudo prompt.
- [x] Проектные venv/collections/temp, фильтрация окружения Ansible, отсутствие dotenv loaders.
- [x] Подготовка Python на чистом сервере, проверка ОС/ресурсов, remote venv.
- [x] Remote kustomize, согласованные remote reads Receptor CA внутри роли;
  custom CA явно отклоняется launcher.
- [x] Скрытый ввод паролей, no_log, запрет неявной смены существующих credentials.
- [x] Проверка AWX JSON из WSL и подтверждение удаления namespace/PVC.
- [x] Русская документация и offline unit tests.

## Настройка оператором до первого запуска

- [ ] Подготовить WSL2 Ubuntu, Python 3.12+/venv/pip, SSH client, Git, CA.
- [ ] Подготовить чистую Ubuntu 24.04+ x86_64, ресурсы и SSH public key.
- [ ] Проверить fingerprint вручную, загрузить passphrase-ключ в WSL-agent.
- [ ] Проверить sudo и маршруты SSH/NodePort из доверенной частной сети.
- [ ] Выполнить отдельный bootstrap контроллера и сохранить исходные пароли в менеджере секретов.
- [ ] Организовать резервное копирование AWX/PostgreSQL и тест восстановления.

## Локальные проверки реализации

- [x] Offline unit tests controller: 11 тестов в Windows и WSL Ubuntu 24.04 / Python 3.12.3.
  После добавления ssh-profile и runtime-dir: 13 тестов пройдены в WSL.
- [x] Offline-тесты переносимого ssh-profile в текущем проекте: 28 тестов пройдены в WSL.
- [x] Статический разбор PowerShell через PowerShell 7 AST parser.
- [x] Bash syntax check всех трёх wrappers в WSL Ubuntu 24.04.
- [x] Bootstrap контроллера в WSL Ubuntu-24.04: установлены закреплённые Python-зависимости
  и kubernetes.core 6.5.0 в проектное окружение.
- [x] Ansible syntax check install/uninstall с закреплёнными зависимостями.
  Назначение inventory из ssh-profile группе awx проверено успешным удалённым запуском.
- [x] YAML parse шести файлов playbooks/roles/requirements через PyYAML в WSL.
- [x] Проверка итогового diff и `git diff --check`.

## Интеграционные сценарии

- [ ] Bootstrap из Windows PowerShell 5.1 и 7, WSL2 Ubuntu, пути проекта с пробелами.
- [ ] Чистая VM без Python: полный запуск от PowerShell до успешного AWX ping.
- [x] Установка закреплённых пакетов/образов: k3s v1.36.3+k3s1, Operator 2.19.1,
  AWX 24.6.1 успешно развёрнуты; это проверка конкретного стенда, не всей матрицы совместимости.
- [ ] Explicit identity и agent; passphrase-ключ; неверный/неизвестный host key;
  сервер только с password auth должен отклоняться.
- [ ] Passwordless sudo, sudo с паролем и root login.
- [ ] Нехватка ресурсов и неподдерживаемая ОС отклоняются до k3s.
- [ ] Повторный запуск с теми же паролями, отказ при других паролях без их раскрытия.
- [ ] Перезагрузка VM: k3s/AWX поднимаются, данные сохраняются.
- [ ] Проверка WSL и браузера Windows, существующего NAT через PublicUrl и ошибочного JSON.
- [ ] Подтверждённое удаление namespace/PVC на тестовой VM, сохранение k3s.
- [ ] Восстановление из backup на другой VM; ограничения local-path задокументированы и приняты.

Реальное удалённое развёртывание выполнено через WSL runner и ssh-profile.
Python на целевом сервере уже присутствовал. Сценарии выше, оставленные без отметок,
не проверены полностью; перезагрузка, удаление и восстановление не выполнялись.

## Текущий запуск через ssh-profile

- [x] Схема рабочего профиля валидна; реальные SSH-вход, pinned host key и passwordless sudo проверены.
- [x] Создан свежий runtime inventory в temp/ через штатный адаптер ssh-profile.
- [x] Передать AWX_ADMIN_PASSWORD и AWX_POSTGRES_PASSWORD из процесса Windows в WSL через WSLENV
  без вывода значений и записи секретов в файлы.
- [x] Добавить запуск controller с --ssh-profile и --agent-socket-file: inventory назначает группу awx,
  сохраняет pinned SSH-настройки и передаёт SSH_AUTH_SOCK процессу Ansible.
- [x] Устранить локальный блокер RPC: временный tmpfs смонтирован в проектный temp/r
  через WSL root без изменения /etc/fstab; Unix socket и запуск Ansible проверены.
  Runner поддерживает --runtime-dir temp/r, внешние пути запрещены.
- [x] Запустить preflight на целевом сервере: SSH, sudo, Ubuntu/архитектура и Python работают.
- [x] Обновить адрес локального профиля по указанию оператора, сохранив доверенный host key;
  SSH и sudo перепроверены, runtime inventory создан заново.
- [x] Расширить раздел /dev/sda3, PV, LV и ext4 после увеличения диска до 50 GiB.
  Корневой LV: 51778682880 байт (48.22 GiB); свободно перед deploy 43853758464 байт.
  Метаданные сохранены на сервере: /root/temp/awx-disk-expansion-zfxv0q7g.
  Начало раздела и /boot сохранены, перезагрузка не потребовалась.
- [x] Повторить deploy: ok=33, changed=13, failed=0, unreachable=0.
- [x] Проверить AWX ping JSON из WSL и отдельно из Windows PowerShell: AWX 24.6.1.
- [x] Проверить k3s active, node Ready, Operator/PostgreSQL/web/task Running;
  PVC PostgreSQL 8Gi Bound на local-path. После установки на / свободно около 34 GiB.
- [ ] Проверить интерактивный вход в браузере; перезагрузку и повторный deploy согласовать отдельно.

## Доработки удобства запуска с Windows

- [ ] Добавить параметры ssh-profile, agent-socket-file и runtime-dir в PowerShell entry point
  (сейчас эти параметры доступны прямому Python runner в WSL).
- [ ] Автоматизировать передачу только разрешённых секретных переменных через WSLENV без вывода значений.
- [ ] Добавить раннюю проверку поддержки Unix-сокетов и понятную инструкцию подготовки tmpfs;
  сейчас монтирование выполняется оператором и теряется при остановке WSL.

## Перед постоянной эксплуатацией

- [ ] Настроить резервное копирование AWX/PostgreSQL, секретов и конфигурации; проверить восстановление.
- [ ] Для доступа вне доверенной частной сети настроить HTTPS и ограничения сетевого доступа.
- [ ] Настроить наблюдение за свободным местом, состоянием k3s/AWX и резервными копиями.
