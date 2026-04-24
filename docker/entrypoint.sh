#!/usr/bin/env bash
# Entrypoint for the disclaimrNG container.
#
# Two roles, selected by the first argument:
#   web    — run Django migrations + collectstatic, then start gunicorn.
#   milter — start the milter daemon listening on $MILTER_SOCKET.
#
# Anything else is exec'd verbatim so you can drop into a shell with
# `docker compose run --rm web bash` or run management commands ad-hoc.

set -euo pipefail

ROLE="${1:-web}"
shift || true

case "$ROLE" in
    web)
        echo "[entrypoint] applying database migrations"
        python manage.py migrate --noinput
        echo "[entrypoint] collecting static files"
        python manage.py collectstatic --noinput
        echo "[entrypoint] starting gunicorn"
        exec gunicorn disclaimrweb.wsgi:application \
            --bind "0.0.0.0:8000" \
            --workers "${GUNICORN_WORKERS:-3}" \
            --access-logfile - \
            --error-logfile -
        ;;
    milter)
        echo "[entrypoint] starting milter daemon on ${MILTER_SOCKET}"
        exec python disclaimr.py --socket "${MILTER_SOCKET}"
        ;;
    manage)
        exec python manage.py "$@"
        ;;
    *)
        exec "$ROLE" "$@"
        ;;
esac
