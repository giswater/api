#!/bin/sh
# Production entrypoint: fix log volume ownership, then drop to the app user.
# Tenant config under /app/config is bind-mounted read-only from the host;
# install.sh sets config/tenants/*.env to mode 644 so the app user can read them.
set -e

mkdir -p /app/logs /app/data/cmms
chown -R app:app /app/logs /app/data/cmms

if [ "$(id -u)" = "0" ]; then
  exec su -s /bin/sh app -c 'cd /app && exec gunicorn -c gunicorn.conf.py app.main:app'
fi

exec gunicorn -c gunicorn.conf.py app.main:app
