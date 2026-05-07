#!/bin/bash
# SmartOLT startup script
# Usage: bash start.sh

set -e

PROJECT_DIR="/root/smart_olt"
VENV="$PROJECT_DIR/env/bin"
LOG_DIR="$PROJECT_DIR/logs"

cd "$PROJECT_DIR"
mkdir -p "$LOG_DIR"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/.env" ]; then
  export $(grep -v '^\s*#' "$PROJECT_DIR/.env" | grep '=' | xargs)
fi

source "$VENV/activate"

# ── Redis ─────────────────────────────────────────────────────────────────────
echo "[1/4] Starting Redis..."
if ! systemctl is-active --quiet redis-server 2>/dev/null; then
  systemctl start redis-server 2>/dev/null || redis-server --daemonize yes \
    --logfile "$LOG_DIR/redis.log" --loglevel notice
fi
echo "      Redis OK"

# ── Django migrations + static ────────────────────────────────────────────────
echo "[2/4] Running migrations..."
python manage.py migrate --noinput

echo "[3/4] Collecting static files..."
python manage.py collectstatic --noinput --clear -v 0

# ── Celery ────────────────────────────────────────────────────────────────────
echo "[4/4] Starting Celery worker + beat..."
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
echo ""
echo "Logs: $LOG_DIR/"
echo "Done. Django is managed by systemctl (smartolt.service)"
