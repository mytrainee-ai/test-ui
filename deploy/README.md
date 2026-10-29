# Деплой на Ubuntu: app.traineeserver.ru

Схема: Nginx принимает HTTPS и проверяет cookie через `auth_service.py`. После успешного входа он проксирует Streamlit, который слушает только `127.0.0.1:8501`. Служба авторизации слушает только `127.0.0.1:8001`. Пользователи и сессии хранятся в SQLite на сервере; загруженные страницы и результаты распознавания в файлы не сохраняются. Этот проект проверен на Ubuntu 26.04.1 LTS с Python 3.14.

## 1. DNS в Timeweb Cloud

Для домена уже установлены NS Timeweb (`ns1.timeweb.ru`, `ns2.timeweb.ru`, `ns3.timeweb.org`, `ns4.timeweb.org`), а корневой домен указывает на `77.232.129.164`. **Менять NS не требуется.**

1. В Timeweb Cloud откройте **Домены и SSL** → `traineeserver.ru` → вкладка **DNS**.
2. Создайте запись типа **A**: хост `app`, значение `77.232.129.164`. Если запись `app` уже есть, измените её. Не создавайте конфликтующую CNAME-запись для `app`.
3. Проверьте: `dig +short app.traineeserver.ru A` должен вернуть `77.232.129.164`. Проверьте также AAAA; если она есть и у сервера нет соответствующего IPv6, удалите неверную AAAA.

Если домен когда-либо перейдёт на сторонние NS, DNS-записи придётся менять у держателя этих NS либо сначала вернуть NS Timeweb в разделе **Домены и SSL** → домен → **Управление** → **NS-серверы**. Перед сменой NS перенесите существующие почтовые и другие записи, иначе связанные сервисы перестанут работать.

## 2. Подготовка Ubuntu

Команды выполняются через SSH пользователем с правами `sudo`. Проверьте отпечаток SSH host key через консоль провайдера перед первым подключением.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git snapd
sudo adduser --system --group --home /var/lib/math-page-app --no-create-home mathpage
sudo mkdir -p /opt/math-page-vision
sudo chown "$USER":"$USER" /opt/math-page-vision
```

Скопируйте исходники проекта в `/opt/math-page-vision` через Git или `rsync`, **не копируя** `.env`, `ssh_creds.txt`, `outputs/`, `.venv/` и тестовые данные. Затем:

```bash
cd /opt/math-page-vision
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
sudo chown -R root:root /opt/math-page-vision
sudo chmod -R o-rwx /opt/math-page-vision
sudo chmod -R g+rX /opt/math-page-vision
sudo chgrp -R mathpage /opt/math-page-vision
```

Секрет API храните в отдельном файле, доступном только root:

```bash
sudo install -m 600 -o root -g root /dev/null /etc/math-page-vision.env
sudo nano /etc/math-page-vision.env
```

Содержимое:

```env
OPENAI_API_KEY=ваш_ключ
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

Второй файл задаёт адрес сервиса входа и путь к базе:

```bash
printf 'APP_ORIGIN=https://app.traineeserver.ru\nAUTH_DB_PATH=/var/lib/math-page-auth/auth.sqlite3\n' | sudo tee /etc/math-page-auth.env >/dev/null
sudo chmod 600 /etc/math-page-auth.env
sudo chown root:root /etc/math-page-auth.env
```

## 3. systemd и Nginx

```bash
sudo cp deploy/math-page-app.service /etc/systemd/system/
sudo cp deploy/math-page-auth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now math-page-app math-page-auth
sudo systemctl status math-page-app math-page-auth --no-pager
sudo cp deploy/nginx-app.conf /etc/nginx/conf.d/math-page.conf
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Проверьте, что локально отвечает служба входа: `curl -I http://127.0.0.1:8001/auth/login`. Streamlit должен отвечать на `http://127.0.0.1:8501`, но его порт не должен быть открыт извне.

Если используется UFW, откройте SSH и веб-порты:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

Проверьте также правила firewall в панели Timeweb Cloud.

## 4. HTTPS

После появления A-записи и доступности порта 80 выпустите сертификат Let's Encrypt. Для Ubuntu используйте Certbot со snap и плагином Nginx:

```bash
sudo snap install core
sudo snap refresh core
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/local/bin/certbot
sudo certbot --nginx -d app.traineeserver.ru --redirect --non-interactive --agree-tos --register-unsafely-without-email
sudo certbot renew --dry-run
```

Если `/usr/local/bin/certbot` уже существует, пропустите создание ссылки. Certbot изменит блок Nginx, добавит TLS и перенаправление HTTP → HTTPS. Для сертификата, выпущенного без email, уведомления о проблемах продления по почте не придут; проверяйте `sudo certbot renew --dry-run` после изменений конфигурации. После этого проверьте `https://app.traineeserver.ru/auth/register`, зарегистрируйтесь, откройте приложение, скачайте Markdown/JSON и выйдите из аккаунта.

## 5. Обновление и диагностика

После обновления кода или `requirements.txt`:

```bash
cd /opt/math-page-vision
sudo systemctl stop math-page-app math-page-auth
sudo chown -R "$USER":"$USER" /opt/math-page-vision
# Обновите исходники выбранным способом.
.venv/bin/python -m pip install -r requirements.txt
sudo chown -R root:root /opt/math-page-vision
sudo chgrp -R mathpage /opt/math-page-vision
sudo chmod -R o-rwx /opt/math-page-vision
sudo chmod -R g+rX /opt/math-page-vision
sudo systemctl start math-page-auth math-page-app
```

Certbot дописывает настройки HTTPS в `/etc/nginx/conf.d/math-page.conf`. При обновлении только Python-кода этот файл не заменяйте исходным `deploy/nginx-app.conf`: он содержит первоначальный HTTP-блок для первого выпуска сертификата.

Логи: `sudo journalctl -u math-page-auth -u math-page-app -f` и `sudo tail -f /var/log/nginx/error.log`. Состояние служб: `systemctl status math-page-auth math-page-app nginx`.

Регистрация открыта всем без подтверждения адреса и восстановления пароля. Это учебный стенд: опубликованный доступ к распознаванию расходует средства API. Для ограничения затрат установите лимит расходов у API-провайдера. Базу `/var/lib/math-page-auth/auth.sqlite3` следует включить в резервное копирование, если нужны сохранённые учётные записи.
