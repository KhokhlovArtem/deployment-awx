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
- [x] Статический разбор PowerShell через PowerShell 7 AST parser.
- [x] Bash syntax check всех трёх wrappers в WSL Ubuntu 24.04.
- [ ] Ansible syntax check с закреплёнными зависимостями при наличии подходящего runtime.
  На момент проверки Ansible в WSL отсутствует; bootstrap не запускался.
- [x] YAML parse шести файлов playbooks/roles/requirements через PyYAML в WSL.
- [x] Проверка итогового diff и `git diff --check`.

## Непроверенные интеграционные сценарии

- [ ] Bootstrap из Windows PowerShell 5.1 и 7, WSL2 Ubuntu, пути проекта с пробелами.
- [ ] Чистая VM без Python: полный запуск от PowerShell до успешного AWX ping.
- [ ] Доступность закреплённых пакетов/образов и совместимость k3s/Operator/AWX.
- [ ] Explicit identity и agent; passphrase-ключ; неверный/неизвестный host key;
  сервер только с password auth должен отклоняться.
- [ ] Passwordless sudo, sudo с паролем и root login.
- [ ] Нехватка ресурсов и неподдерживаемая ОС отклоняются до k3s.
- [ ] Повторный запуск с теми же паролями, отказ при других паролях без их раскрытия.
- [ ] Перезагрузка VM: k3s/AWX поднимаются, данные сохраняются.
- [ ] Проверка WSL и браузера Windows, существующего NAT через PublicUrl и ошибочного JSON.
- [ ] Подтверждённое удаление namespace/PVC на тестовой VM, сохранение k3s.
- [ ] Восстановление из backup на другой VM; ограничения local-path задокументированы и приняты.

Реальное удалённое развёртывание не выполнялось. Отметки интеграционных пунктов
ставятся только после проверки на выделенной тестовой инфраструктуре.
