# SmartOLT Cloud

A full-featured Django web application for ISP/NOC teams to manage, monitor, and provision ZTE and Huawei OLTs and ONTs — a self-hosted alternative to SmartOLT.

## Features

- **OLT Management** — Register ZTE (C300/C320/C600) and Huawei (MA5600T/MA5800) OLTs with SNMP and Telnet connectivity
- **ONT Lifecycle** — Discover unregistered ONUs, provision via Telnet CLI, reboot/factory-reset remotely
- **Real-time Monitoring** — Signal (RX/TX/OLT-RX), traffic, CPU/memory/temperature history charts
- **Alert Rules** — Configurable thresholds with email notification dispatch
- **Event Log** — Structured event history with severity levels and acknowledgement
- **Reports & Export** — HTML reports and CSV export for ONT status and events
- **Multi-user** — OLT ownership, per-user quota, superuser admin panel
- **Background Polling** — Celery + Redis fan-out polling for 1 000+ OLTs at 5-minute intervals

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 4.2 |
| SNMP | pysnmp (v2c, pure Python) |
| CLI | Raw Telnet socket (ZTE & Huawei vendors) |
| Task Queue | Celery 5 + Redis |
| Beat Scheduler | django-celery-beat |
| Frontend | Bootstrap 5.3, Chart.js, DataTables |
| Database | SQLite (default) — swap to PostgreSQL for production |
| Static Files | WhiteNoise |

## Quick Start

### 1. Clone & set up environment

```bash
git clone <repo-url> smart_olt
cd smart_olt
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure `.env`

Copy the template and edit as needed:

```bash
cp .env.example .env   # or create .env manually
```

Key variables:

```ini
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Redis (required for Celery background polling)
REDIS_URL=redis://localhost:6379/0

# Disable Celery for simple single-process testing
USE_CELERY=False

# Email (optional — console backend is default)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your@email.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=SmartOLT <your@email.com>
```

### 3. Initialize database

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

### 4. Create admin user

```bash
python manage.py createsuperuser
```

### 5. Run development server

**Without Celery (synchronous, no Redis needed):**

```bash
# Set USE_CELERY=False in .env
python manage.py runserver
```

**With Celery (full background polling):**

```bash
# Terminal 1 — Django
python manage.py runserver

# Terminal 2 — Celery worker
celery -A smartolt worker -l info --concurrency=20

# Terminal 3 — Celery beat scheduler
celery -A smartolt beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Production Deployment (Ubuntu)

Run the included script for a guided production setup (systemd + gunicorn on port 8001):

```bash
chmod +x setup.sh && sudo ./setup.sh
```

The script:
1. Creates a Python virtualenv and installs dependencies
2. Runs migrations and collects static files
3. Registers a `smartolt.service` systemd unit

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | insecure dev key | Django secret key — **change in production** |
| `DEBUG` | `True` | Django debug mode |
| `ALLOWED_HOSTS` | `*` | Comma-separated allowed hostnames |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `USE_CELERY` | `True` | Enable Celery background tasks |
| `OLT_SSH_TIMEOUT` | `30` | Telnet session timeout (seconds) |
| `OLT_SSH_MAX_CONCURRENT` | `50` | Max concurrent Telnet sessions |
| `CELERY_CONCURRENCY` | `20` | Celery worker concurrency |
| `EMAIL_BACKEND` | console | Django email backend class |
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP host |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_USE_TLS` | `True` | SMTP TLS |
| `EMAIL_HOST_USER` | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | — | SMTP password |
| `DEFAULT_FROM_EMAIL` | `SmartOLT <noreply@smartolt.local>` | Sender address |

## SNMP Configuration

SmartOLT uses **SNMPv2c** to query OLT status and ONU optical levels.

On each OLT, enable SNMP with a read community string (e.g. `public`) and ensure UDP port 161 is reachable from the server.

| Vendor | OIDs used |
|--------|-----------|
| ZTE ZXAN | `1.3.6.1.4.1.3902.*` (GPON ONU oper-state, serial, Rx/Tx power) |
| Huawei MA56xx/MA58xx | `1.3.6.1.4.1.2011.6.128.*` (ONU run-state, serial, Rx/Tx power) |
| Any (MIB-II) | `1.3.6.1.2.1.1.1.0` sysDescr, `1.3.6.1.2.1.1.3.0` sysUpTime |

## Telnet / CLI Configuration

CPU, memory, temperature, provisioning, and ONT commands are sent over Telnet (default port 23). Enable Telnet management on the OLT and ensure port 23 is reachable.

Supported operations per vendor:

| Operation | ZTE | Huawei |
|-----------|-----|--------|
| Version / uptime | `show version` | `display version` |
| CPU usage | `show cpu` | `display cpu-usage` |
| Memory usage | `show memory` | `display memory-usage` |
| Temperature | `show temperature` | `display temperature 0` |
| ONT list | `show gpon onu state …` | `display ont info …` |
| ONT optical | `show gpon onu optical-info …` | `display ont optical-info …` |
| Provision ONT | `interface gpon-onu_…` sequence | `interface gpon …` + `service-port` |
| Reboot ONT | `interface gpon-onu_…\nreboot` | `interface gpon …\nont reset` |
| Factory reset | `interface gpon-onu_…\nfactory-reset` | `interface gpon …\nont factory-reset` |
| Discover uncfg | `show gpon onu uncfg …` | `display ont autofind …` |

## URL Map

| Path | Description |
|------|-------------|
| `/` | Dashboard (stats, charts, recent events) |
| `/olts/` | OLT list / add / detail / edit / delete |
| `/olts/<id>/sync-device/` | Sync PON ports + ONTs from live device |
| `/olts/<id>/scan-all/` | Scan all PON ports for unregistered ONUs |
| `/olts/<id>/snmp-live/` | Live SNMP ONU table (JSON) |
| `/onts/` | ONT list with filters |
| `/onts/quick-register/` | Register & provision a new ONT (JSON POST) |
| `/onts/<id>/reboot/` | Reboot ONT via Telnet (JSON POST) |
| `/onts/<id>/factory-reset/` | Factory reset ONT (JSON POST) |
| `/monitoring/signals/` | Signal quality overview |
| `/monitoring/traffic/` | Traffic overview |
| `/monitoring/events/` | Event log with filters |
| `/alerts/rules/` | Alert rule CRUD |
| `/alerts/history/` | Notification history |
| `/reports/` | HTML reports + CSV export |
| `/accounts/` | Login, register, profile, user management |
| `/admin/` | Django admin panel |

> **Change all passwords before deploying to production.**

## Project Structure

```
smart_olt/
├── smartolt/           # Django project (settings, urls, celery)
├── accounts/           # User auth, profiles, quotas
├── olts/               # OLT models, SNMP service, Telnet service, Celery tasks
├── onts/               # ONT models, profiles, provisioning
├── monitoring/         # Signal/traffic/event history, chart APIs
├── alerts/             # Alert rules, notification dispatch, Celery tasks
├── reports/            # HTML reports, CSV export
├── core/               # Dashboard, global stats API, demo seed command
├── templates/          # Bootstrap 5 server-rendered templates
├── static/             # CSS, JS
├── requirements.txt
├── setup.sh            # Ubuntu production setup
├── start.sh            # Dev/test start script
└── manage.py
```
