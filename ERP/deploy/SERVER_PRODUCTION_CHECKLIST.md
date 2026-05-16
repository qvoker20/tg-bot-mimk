# ERP Production Checklist (Ubuntu + Nginx + Gunicorn + PgBouncer)

## 1. Що вже зроблено в коді

Реалізовано в коміті `d33dd2a`:

- `ERP/app/main.py`
  - Прибрано запуск `schedule_cutoff_worker` з `lifespan` (тепер це окремий cron job).
- `ERP/run_cutoff.py`
  - Додано скрипт для щоденного cutoff запуску.
- `ERP/app/modules/assemblers/db/async_connection.py`
  - Додано режим `USE_PGBOUNCER=1` для вимкнення внутрішнього SQLAlchemy pooling (`NullPool`).
- `ERP/requirements.txt`
  - Додано `gunicorn`, `redis`, `rq`.
- `ERP/app/main.py`
  - Додано `/healthz` з DB probe (`503`, якщо БД недоступна).
- `ERP/worker_rq.py`, `ERP/app/tasks/*`
  - Додано базовий каркас для винесення heavy jobs у RQ/Redis.
- `ERP/deploy/systemd/api_app.service.example`
  - Додано приклад systemd-сервісу.
- `ERP/deploy/pgbouncer/pgbouncer.ini.example`
  - Додано приклад конфігу PgBouncer.
- `ERP/deploy/nginx/api_rate_limit.conf.example`
  - Додано приклад nginx rate-limit/connection-limit.
- `ERP/deploy/fail2ban/*`
  - Додано jail + filter для блокування хвиль 4xx/429.
- `ERP/deploy/firewall/ufw_setup.sh`
  - Додано базовий скрипт UFW.
- `ERP/deploy/logrotate/erp-api.conf`
  - Додано logrotate для cron/gunicorn/nginx.
- `ERP/deploy/backup/postgres_backup.sh`, `ERP/deploy/backup/postgres_restore.sh`
  - Додано backup/restore скрипти PostgreSQL.
- `ERP/deploy/monitoring/prometheus.yml`, `ERP/deploy/monitoring/alert_rules.yml`
  - Додано стартовий конфіг Prometheus + алерти.

---

## 2. Що обов'язково зробити на сервері

> Приклад для Ubuntu 22.04/24.04.

### 2.1. Підготувати середовище

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx postgresql-client pgbouncer
```

```bash
cd /full/path/to/project/ERP
python3 -m venv /full/path/to/project/.venv
source /full/path/to/project/.venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.2. Налаштувати `.env`

Мінімально перевірити/додати:

```env
# FastAPI
ERP_RELOAD=0
ERP_HOST=127.0.0.1

# DB через PgBouncer
PG_HOST=127.0.0.1
PG_PORT=6432
USE_PGBOUNCER=1

# Безпека
SECRET_KEY=very-long-random-secret
SESSION_COOKIE_SECURE=1
SESSION_COOKIE_SAMESITE=lax
```

### 2.3. Налаштувати PgBouncer

```bash
sudo cp /full/path/to/project/ERP/deploy/pgbouncer/pgbouncer.ini.example /etc/pgbouncer/pgbouncer.ini
```

Відредагувати `/etc/pgbouncer/pgbouncer.ini`:
- виставити реальну БД, користувача, параметри пулу.

Створити `/etc/pgbouncer/userlist.txt` (формат: `"username" "md5..."`).

```bash
sudo systemctl restart pgbouncer
sudo systemctl enable pgbouncer
sudo systemctl status pgbouncer
```

### 2.4. Налаштувати systemd для API (Gunicorn + UvicornWorker)

```bash
sudo cp /full/path/to/project/ERP/deploy/systemd/api_app.service.example /etc/systemd/system/api_app.service
sudo nano /etc/systemd/system/api_app.service
```

В `ExecStart` перевірити:
- правильний шлях до `.venv/bin/gunicorn`
- правильний `WorkingDirectory`
- `-w` за формулою: `(CPU * 2) + 1`

Потім:

```bash
sudo systemctl daemon-reload
sudo systemctl enable api_app
sudo systemctl start api_app
sudo systemctl status api_app
journalctl -u api_app -f
```

### 2.5. Налаштувати cron для cutoff

```bash
crontab -e
```

Додати:

```cron
5 18 * * * /full/path/to/project/.venv/bin/python /full/path/to/project/ERP/run_cutoff.py >> /var/log/api_cron.log 2>&1
```

Перевірка:

```bash
tail -f /var/log/api_cron.log
```

### 2.6. Налаштувати Nginx

У вашому `server` блоці:

```nginx
client_header_buffer_size 16k;
large_client_header_buffers 4 32k;
keepalive_timeout 65;

location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Застосувати:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 2.7. Увімкнути rate limit на Nginx

```bash
sudo cp /full/path/to/project/ERP/deploy/nginx/api_rate_limit.conf.example /etc/nginx/sites-available/your_site
sudo nginx -t
sudo systemctl reload nginx
```

### 2.8. Увімкнути Fail2ban

```bash
sudo apt install -y fail2ban
sudo cp /full/path/to/project/ERP/deploy/fail2ban/jail.local.example /etc/fail2ban/jail.local
sudo mkdir -p /etc/fail2ban/filter.d
sudo cp /full/path/to/project/ERP/deploy/fail2ban/filter.d/nginx-erp-4xx.conf /etc/fail2ban/filter.d/nginx-erp-4xx.conf
sudo systemctl restart fail2ban
sudo systemctl enable fail2ban
sudo fail2ban-client status
```

### 2.9. Увімкнути firewall (UFW)

```bash
sudo bash /full/path/to/project/ERP/deploy/firewall/ufw_setup.sh
```

### 2.10. Увімкнути logrotate

```bash
sudo cp /full/path/to/project/ERP/deploy/logrotate/erp-api.conf /etc/logrotate.d/erp-api
sudo logrotate -d /etc/logrotate.d/erp-api
```

### 2.11. Налаштувати backup PostgreSQL

Тест ручного backup:

```bash
chmod +x /full/path/to/project/ERP/deploy/backup/postgres_backup.sh
DB_NAME=your_db DB_USER=your_user DB_HOST=127.0.0.1 DB_PORT=5432 /full/path/to/project/ERP/deploy/backup/postgres_backup.sh
```

Щоденний backup (02:30):

```cron
30 2 * * * DB_NAME=your_db DB_USER=your_user DB_HOST=127.0.0.1 DB_PORT=5432 /full/path/to/project/ERP/deploy/backup/postgres_backup.sh >> /var/log/postgres_backup.log 2>&1
```

### 2.12. Увімкнути worker для heavy jobs (RQ)

Додати Redis:

```bash
sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

Приклад systemd для RQ worker (`/etc/systemd/system/erp-rq-worker.service`):

```ini
[Unit]
Description=ERP RQ Worker
After=network.target redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/full/path/to/project/ERP
Environment="PATH=/full/path/to/project/.venv/bin"
EnvironmentFile=/full/path/to/project/.env
ExecStart=/full/path/to/project/.venv/bin/python /full/path/to/project/ERP/worker_rq.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable erp-rq-worker
sudo systemctl start erp-rq-worker
sudo systemctl status erp-rq-worker
```

---

## 3. Що ще додати для стабільного масштабування

### 3.1. Моніторинг та алерти (обов'язково)

- Prometheus + Grafana (CPU, RAM, RPS, latency p95/p99, 5xx).
- PostgreSQL exporter + PgBouncer exporter.
- Sentry для винятків FastAPI.

### 3.2. Ліміти та захист

- Rate limiting на Nginx (особливо `/login`, API з записом).
- Fail2ban для brute-force.
- Firewall (тільки 80/443 зовні; 5432/6432 локально).

### 3.3. Надійність процесів

- `Restart=always` вже є; додати `RestartSec=3`.
- Додати healthcheck endpoint (`/healthz`) і перевірку БД.
- Налаштувати logrotate для `api_cron.log` та gunicorn/nginx логів.

### 3.4. База даних

- Регулярні бекапи (`pg_dump` + retention policy).
- Тюнінг PostgreSQL (`max_connections`, `shared_buffers`, `work_mem`) під RAM.
- Перевірка індексів на запити з найбільшим навантаженням.

### 3.5. Фонові важкі задачі

- Якщо розрахунки стануть важкими: винести в Celery/RQ + Redis.
- Не виконувати CPU-heavy обчислення в API-процесах.

---

## 4. Швидкий smoke-test після деплою

```bash
# 1) API живий
curl -I http://127.0.0.1:8000/

# 2) systemd процес живий
systemctl is-active api_app

# 3) PgBouncer живий
systemctl is-active pgbouncer

# 4) Nginx валідний
nginx -t

# 5) Cron скрипт відпрацьовує вручну
/full/path/to/project/.venv/bin/python /full/path/to/project/ERP/run_cutoff.py

# 6) Healthcheck readiness (повинен повертати 200)
curl -i http://127.0.0.1:8000/healthz

# 7) RQ worker живий
systemctl is-active erp-rq-worker
```

Якщо всі 5 пунктів успішні, базова production-конфігурація готова.
