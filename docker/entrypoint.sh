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

# Private CA for ldaps:// (Active Directory): compose mounts ./certs at /etc/ssl/ad.
# An explicit LDAPTLS_CACERT wins; without the file nothing changes.
if [ -z "${LDAPTLS_CACERT:-}" ] && [ -f /etc/ssl/ad/ad-ca.pem ]; then
    export LDAPTLS_CACERT=/etc/ssl/ad/ad-ca.pem
    echo "[entrypoint] LDAPS: trusting the CA in /etc/ssl/ad/ad-ca.pem"
fi

ROLE="${1:-web}"
shift || true

case "$ROLE" in
    web)
        echo "[entrypoint] applying database migrations"
        python manage.py migrate --noinput
        echo "[entrypoint] collecting static files"
        python manage.py collectstatic --noinput
        echo "[entrypoint] bootstrapping admin user (no-op if one exists)"
        python manage.py bootstrap_admin
        # Tenants must exist before directory_servers so the FK link
        # (LDAP_SERVER_<HANDLE>_TENANT=<slug>) can resolve.
        if [ -n "${TENANTS:-}" ]; then
            echo "[entrypoint] syncing tenants from TENANTS"
            python manage.py sync_tenants ${TENANT_SYNC_PRUNE:+--prune}
        fi
        if [ -n "${LDAP_SERVERS:-}" ]; then
            echo "[entrypoint] syncing directory servers from LDAP_SERVERS"
            python manage.py sync_directory_servers ${LDAP_SYNC_PRUNE:+--prune}
        fi
        echo "[entrypoint] starting gunicorn"
        # --worker-tmp-dir: the heartbeat file belongs in tmpfs, on a disk-backed
        # container filesystem it can block a worker (gunicorn docs).
        exec gunicorn disclaimrweb.wsgi:application             --worker-tmp-dir /dev/shm \
            --bind "0.0.0.0:8000" \
            --workers "${GUNICORN_WORKERS:-3}" \
            --access-logfile - \
            --error-logfile -
        ;;
    milter)
        MILTER_SOCKET="${MILTER_SOCKET:-inet:0.0.0.0:5000}"
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
