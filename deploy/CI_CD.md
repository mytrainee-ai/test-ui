# Автоматический деплой через GitHub Actions

Для `mytrainee-ai/test-ui` используется один workflow: pull request запускает тесты, push в `main` запускает тесты и затем деплой. GitHub не получает ключ API, пароль root или базу пользователей. На сервер передаётся только SHA коммита; сервер сам скачивает публичный репозиторий и готовит релиз.

## Что делает workflow

1. GitHub Actions устанавливает Python 3.14 и зависимости, запускает `python -m unittest -q test_local test_auth`.
2. Если тесты успешны и событие — push в `main`, Actions подключается к серверу по отдельному SSH-ключу пользователя `mathdeploy`.
3. `/usr/local/bin/math-page-deploy` скачивает точный коммит, создаёт для него окружение `.venv`, устанавливает зависимости и повторяет тесты на Ubuntu.
4. `/usr/local/sbin/math-page-activate` переключает ссылку `/opt/math-page-ci/current`, перезапускает две службы и проверяет вход через HTTPS. Если проверка не проходит, ссылка возвращается на предыдущий релиз.
5. Предыдущий рабочий релиз доступен через `sudo /usr/local/sbin/math-page-rollback`.

## Разовая подготовка сервера

Нужен пользователь `mathdeploy` без пароля root. У него есть право записывать только `/opt/math-page-ci` и запускать два фиксированных root-скрипта через `sudo` без пароля. На текущем сервере пользователь и скрипты уже установлены. Приватный ключ доступа из GitHub Actions устанавливается в секрет окружения `production` под именем `DEPLOY_SSH_KEY`; публичный ключ помещён в `/home/mathdeploy/.ssh/authorized_keys`. SSH host key уже проверен и закреплён в workflow.

В репозитории откройте **Settings → Environments → production → Environment secrets → Add secret**. Вставьте полное содержимое локального файла `C:\Users\valery\.ssh\math-page-actions-deploy` как значение `DEPLOY_SSH_KEY`. Этот файл не добавляйте в Git и не отправляйте в чат. На Windows текст можно скопировать командой `Get-Content -Raw C:\Users\valery\.ssh\math-page-actions-deploy | Set-Clipboard`.

Исходные API-настройки остаются в `/etc/math-page-vision.env`, а база пользователей — в `/var/lib/math-page-auth/auth.sqlite3`. Nginx и Certbot при обычном деплое не меняются.

Текущая ручная установка уже переведена на `deploy/math-page-app-ci.service` и `deploy/math-page-auth-ci.service`. Исходный `/opt/math-page-vision` сохранён как запасной вариант. Скрипты `bootstrap-ci.sh` и `migrate-ci.sh` фиксируют разовую настройку для повторения на новом сервере.

## Работа после настройки

- `git push origin main` запускает тесты и деплой. Текущий результат виден в GitHub → **Actions**.
- На сервере активный релиз: `readlink -f /opt/math-page-ci/current`.
- Откат: `sudo /usr/local/sbin/math-page-rollback`.
- Логи: `sudo journalctl -u math-page-app -u math-page-auth -n 100 --no-pager`.

В каталоге `/opt/math-page-ci/releases` хранятся отдельные окружения релизов. После успешного деплоя скрипт сохраняет текущий, предыдущий и ещё один недавний релиз; более старые worktree удаляются. Текущий и предыдущий релизы очистка не затрагивает.
