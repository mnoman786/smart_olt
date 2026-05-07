#!/bin/bash
# SmartOLT startup script
# Usage: bash start.sh [--prod]
# Default: Django dev server on port 8000
# --prod:  Gunicorn on port 8000

set -e

PROJECT_DIR="/root/smart_olt"
VENV="$PROJECT_DIR/env/bin"
LOG_DIR="$PROJECT_DIR/logs"
PROD=false

for arg in "$@"; do
  [ "$arg" = "--prod" ] && PROD=true
done

cd "$PROJECT_DIR"
mkdir -p "$LOG_DIR"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/.env" ]; then
  export $(grep -v '^\s*#' "$PROJECT_DIR/.env" | grep '=' | xargs)
fi

source "$VENV/activate"

# ── Redis ─────────────────────────────────────────────────────────────────────
echo "[1/5] Starting Redis..."
if ! systemctl is-active --quiet redis-server 2>/dev/null; then
  systemctl start redis-server 2>/dev/null || redis-server --daemonize yes \
    --logfile "$LOG_DIR/redis.log" --loglevel notice
fi
echo "      Redis OK"

# ── Django migrations + static ────────────────────────────────────────────────
echo "[2/5] Running migrations..."
python manage.py migrate --noinput

echo "[3/5] Collecting static files..."
python manage.py collectstatic --noinput --clear -v 0

# ── Kill any previous Celery processes ────────────────────────────────────────
echo "[4/5] Starting Celery worker + beat..."
pkill -f "celery.*smartolt" 2>/dev/null || true
sleep 1

celery -A smartolt worker \
  --loglevel=info \
  --concurrency="${CELERY_CONCURRENCY:-10}" \
  --logfile="$LOG_DIR/celery-worker.log" \
  --pidfile="$LOG_DIR/celery-worker.pid" \
  --detach

celery -A smartolt beat \
  --loglevel=info \
  --scheduler django_celery_beat.schedulers:DatabaseScheduler \
  --logfile="$LOG_DIR/celery-beat.log" \
  --pidfile="$LOG_DIR/celery-beat.pid" \
  --detach

echo "      Celery worker & beat started"

# ── Django / Gunicorn ─────────────────────────────────────────────────────────
echo "[5/5] Starting web server..."

if [ "$PROD" = true ]; then
  # Production: gunicorn (install with: pip install gunicorn)
  pkill -f "gunicorn.*smartolt" 2>/dev/null || true
  gunicorn smartolt.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile "$LOG_DIR/gunicorn-access.log" \
    --error-logfile  "$LOG_DIR/gunicorn-error.log" \
    --daemon
  echo "      Gunicorn started on http://0.0.0.0:8000"
else
  echo "      Django dev server on http://0.0.0.0:8000"
  echo "      Logs: $LOG_DIR/"
  echo ""
  python manage.py runserver 0.0.0.0:8000
fi
