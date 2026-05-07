#!/bin/bash
# SmartOLT stop script

echo "Stopping Celery worker & beat..."
pkill -f "celery.*smartolt" 2>/dev/null && echo "  Celery stopped" || echo "  Celery was not running"

echo "Stopping Gunicorn..."
pkill -f "gunicorn.*smartolt" 2>/dev/null && echo "  Gunicorn stopped" || echo "  Gunicorn was not running"

echo "Done."
