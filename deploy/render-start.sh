#!/usr/bin/env bash
set -euo pipefail

# Run AI worker in a restart loop so queue processing survives transient crashes.
(
  while true; do
    python manage.py run_worker
    sleep "${AI_WORKER_RESTART_DELAY:-2}"
  done
) &

# Start Django web process in foreground.
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 180
