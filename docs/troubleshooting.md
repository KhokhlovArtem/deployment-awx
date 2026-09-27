# Диагностика

## До подключения

- `Host key verification failed`: выполните ручной первый SSH-вход по процедуре
  [README](../README.md#1-подготовить-wsl-и-доверие-ssh). При смене fingerprint сначала
  выясните причину и подтвердите новый отпечаток у администратора; не отключайте проверку.
- `Permission denied (publickey)`: проверьте пользователя, порт, установленный публичный
  ключ и абсолютный WSL-путь `--identity`. Passphrase-ключ загрузите в WSL-agent.
  `BatchMode` не запрашивает пароль ключа. При запуске из PowerShell agent интерактивной
  WSL-сессии может быть недоступен — запустите runner в этой сессии.
- Требуется sudo: добавьте `-K` / `-AskBecomePass`, либо настройте sudo самостоятельно.
- Нет `.venv`: выполните bootstrap; отсутствующие системные пакеты WSL установите отдельно.
- Ошибка runtime directory: проверьте, что `temp/`, `.ansible/`, `.venv/` — обычные каталоги
  проекта, не symlink/junction наружу. Не перенаправляйте temp за пределы репозитория.
- Ошибка скрытого assert credentials при повторе: передайте исходные пароли AWX/PostgreSQL.
  Не включайте debug/diff и не выводите Secrets для диагностики.

## На сервере

Следующие команды выполняются вручную **на удалённой Ubuntu**, не в WSL.
Примеры используют namespace `awx`; замените его, если выбрали другой.

```bash
sudo systemctl status k3s
sudo kubectl get nodes
sudo kubectl get pods -n awx
sudo kubectl get svc -n awx
sudo kubectl get pvc -n awx
sudo kubectl describe awx awx -n awx
```

Kubeconfig остаётся на сервере и не копируется на контроллер.
При ImagePullBackOff проверьте доступ сервера к registry и существование закреплённых тегов.
Для kube-rbac-proxy используется зеркало из `roles/awx/templates/kustomization.yaml.j2`;
настройки образа находятся в `roles/awx/defaults/main.yml`.

## AWX готов на сервере, но runner завершился ошибкой

Проверка из WSL требует настоящего JSON `/api/v2/ping/` с признаками AWX.
Проверьте маршрут из WSL, NodePort сервиса, существующие правила firewall/NAT
и заданный `--public-url`. Redirect и HTML от обратного прокси не считаются успехом.
Launcher не изменяет сетевые правила. Для HTTP используйте доверенную частную сеть.
Проверка браузера Windows выполняется отдельно: успешный запрос из WSL её не заменяет.

Повторите ту же команду с прежними паролями после устранения причины.
Переустановка не выполняет upgrade k3s. Параметры удаления и ограничения хранения —
в [README](../README.md#хранение-резервные-копии-и-удаление).
