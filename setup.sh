#!/bin/bash
# SmartOLT — full server setup + systemd service
# Usage: bash setup.sh
# Run as root from /root/smart_olt

set -e

APP_DIR="/root/smart_olt"
ENV_DIR="$APP_DIR/env"
PYTHON="$ENV_DIR/bin/python"
PIP="$ENV_DIR/bin/pip"
SERVICE_NAME="smartolt"
PORT="8001"
USER="root"

echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip curl

echo "==> Creating virtual environment..."
python3 -m venv "$ENV_DIR"

echo "==> Installing Python dependencies..."
$PIP install --upgrade pip -q
$PIP install -r "$APP_DIR/requirements.txt" -q

echo "==> Running migrations..."
$PYTHON "$APP_DIR/manage.py" migrate --noinput

echo "==> Collecting static files..."
$PYTHON "$APP_DIR/manage.py" collectstatic --noinput

echo "==> Loading demo data (skip if DB already seeded)..."
$PYTHON "$APP_DIR/manage.py" seed_demo 2>/dev/null || echo "   (seed skipped — data already exists)"

echo "==> Creating systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=SmartOLT Django App
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON $APP_DIR/manage.py runserver 0.0.0.0:$PORT
Restart=always
RestartSec=5
Environment=DJANGO_SETTINGS_MODULE=smartolt.settings

[Install]
WantedBy=multi-user.target
EOF

echo "==> Enabling and starting service..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

echo ""
echo "==> Done. Service status:"
systemctl status $SERVICE_NAME --no-pager

echo ""
echo "   App running at: http://$(hostname -I | awk '{print $1}'):$PORT"
echo "   Login: admin / admin123"
