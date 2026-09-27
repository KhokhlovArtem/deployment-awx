# ssh-profile — переносимая папка подключения

**Копируйте этот каталог целиком в корень другого проекта.** Затем достаточно
сказать модели:

> Для подключения к серверу используй каталог `ssh-profile`.
> Сначала прочитай `ssh-profile/AGENTS.md` и `ssh-profile/README.md`.
> Проверь доступ, затем выполняй только поставленную задачу проекта.

Папка не предоставляет разрешение менять сервер сама по себе.

## Состав

```text
ssh-profile/
├── AGENTS.md                    # порядок работы для модели
├── README.md                    # быстрый старт и перенос
├── GUIDE.md                     # схема, экспорт, SSH-agent, безопасность
├── TEST-REPORT.md               # результаты и ограничения испытаний
├── .gitignore                   # защита локального профиля при переносе
├── server-access.local.yml      # рабочее подключение, НЕ в Git
├── server-access.example.yml    # шаблон без реального подключения
├── server_access.py             # самостоятельная утилита
├── requirements.txt             # PyYAML; Python 3.11+
└── tests/test_server_access.py  # автономные offline-тесты
```

Рабочий профиль хранит адрес, порт, пользователя, fingerprint ключа пользователя
и доверенный публичный ключ сервера. **Паролей, закрытых ключей, путей к старому
проекту и сокета агента в нём нет.** На новой машине нужен соответствующий ключ
в локальном SSH-agent; копирование папки само по себе не выдаёт доступ.

Существующий `server-access.local.yml` готов к использованию. Не заменяйте его
шаблоном и не экспортируйте заново без причины. Профиль содержит внутренние
сведения об инфраструктуре: переносите его доверенным способом, не публикуйте.

## Быстрый старт

Все команды выполняются **из корня принимающего проекта**, не из этой папки.
Рабочая среда: Linux или WSL с `ssh`, `ssh-add`, `ssh-keygen`; Python 3.11+.
Native Windows поддерживает только offline-валидацию.

Используйте имеющуюся `.venv` принимающего проекта. Если окружения нет, создайте
его локально. Не копируйте виртуальное окружение из другого проекта. Пример
подготовки для нового проекта (сначала убедитесь, что пути не ведут наружу через symlink):

```bash
mkdir -p temp
export TMPDIR="$PWD/temp" TMP="$PWD/temp" TEMP="$PWD/temp"
export PIP_CACHE_DIR="$PWD/temp/pip-cache" XDG_CACHE_HOME="$PWD/temp/cache"

# Только если .venv ещё отсутствует:
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r ssh-profile/requirements.txt
```

В корневом `.gitignore` принимающего проекта исключите `temp/` и `.venv/`, включая
вложенные каталоги. Локальный профиль защищён собственным `.gitignore` этой папки.

```bash
# Проверка схемы без сети:
python ssh-profile/server_access.py validate

# Проверка реального подключения и sudo через SSH-agent:
python ssh-profile/server_access.py check

# Создать inventory для задач Ansible (если проект использует Ansible):
python ssh-profile/server_access.py ansible --output-dir temp/ssh-profile-session
```

Утилита сама находит `server-access.local.yml` рядом с собой. Она не читает `.env`
и не требует данных исходного bootstrap. Зависимости Ansible относятся к
принимающему проекту и не устанавливаются автоматически этим комплектом.

## Использование Ansible

```bash
ansible all -i temp/ssh-profile-session/inventory.yml \
  -m ansible.builtin.command -a '/usr/bin/id -un'

ansible all -i temp/ssh-profile-session/inventory.yml \
  -m ansible.builtin.command -a '/usr/bin/id -u' --become

# Только после разрешения оператора на задачи playbook:
ansible-playbook -i temp/ssh-profile-session/inventory.yml path/to/project-playbook.yml
```

Путь `--output-dir` должен быть новым; существующие артефакты не перезаписываются.
По умолчанию это `temp/ssh-profile`. При повторной генерации выберите новое имя.
Параметры Ansible не включают become для всех задач автоматически.

## Что важно при переносе

- Переносится сама папка, **включая игнорируемый `server-access.local.yml` и скрытый `.gitignore`**.
  Обычный Git clone/checkout не принесёт рабочий профиль — только код и инструкции.
- `temp/`, `.venv`, private keys и ссылки на сокеты не переносите. Runtime создавайте
  из корня принимающего проекта, чтобы он оставался за пределами переносимой папки.
- SSH-agent должен быть доступен процессу через `SSH_AUTH_SOCK`. Адрес сокета
  из другого терминала автоматически не появляется в новом процессе.
- При нехватке агента или несовпадении host key остановитесь; не отключайте проверки.
- Настройка приложений, служб, firewall и пользователей не входит в команду check.

## Самопроверка комплекта

```bash
python -m unittest discover -s ssh-profile/tests -v
```

Подробнее: [GUIDE.md](GUIDE.md). Проверенные сценарии и ограничения:
[TEST-REPORT.md](TEST-REPORT.md). Внешние файлы исходного bootstrap-проекта
не нужны для использования уже подготовленного подключения.
