#!/bin/sh
# Production entrypoint: fix log/file volume ownership, then drop to the app user
# and exec the image/Compose command (gunicorn, celery worker, celery beat, …).
# Tenant config under /app/config is bind-mounted read-only from the host;
# install.sh sets config/tenants/*.env to mode 644 so the app user can read them.
set -e

mkdir -p /app/logs /app/data/files
chown -R app:app /app/logs /app/data/files

if [ "$#" -eq 0 ]; then
  set -- gunicorn -c gunicorn.conf.py app.main:app
fi

if [ "$(id -u)" = "0" ]; then
  exec su -s /bin/sh -c 'cd /app && exec "$0" "$@"' app -- "$@"
fi

cd /app
exec "$@"
