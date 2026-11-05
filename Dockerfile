# syntax=docker/dockerfile:1.7

# ---- builder ---------------------------------------------------------------
# Builds the wheels we need on top of the slim runtime base. Build-only deps
# (gcc, *-dev headers) stay in this stage so they do not bloat the final image.

FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libldap2-dev \
        libsasl2-dev \
        libxml2-dev \
        libxslt1-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY LICENSE ./

# Install dependencies into an isolated prefix so the runtime stage can copy
# them as a single layer.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .


# ---- assets ----------------------------------------------------------------
# Monaco + TinyMCE from the npm registry (pinned, sha512-verified), so the
# template editor works without a CDN. Needs internet at *build* time only.

FROM python:3.12-slim-bookworm AS assets
COPY docker/fetch_editor_assets.py /fetch_editor_assets.py
RUN python /fetch_editor_assets.py /vendor


# ---- runtime ---------------------------------------------------------------

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=disclaimrweb.settings

RUN apt-get update && apt-get install -y --no-install-recommends \
        libldap-2.5-0 \
        libsasl2-2 \
        libxml2 \
        libxslt1.1 \
        libpq5 \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 disclaimr \
    && useradd --system --uid 1000 --gid disclaimr --home-dir /app --shell /usr/sbin/nologin disclaimr

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY --chown=disclaimr:disclaimr disclaimr ./disclaimr
COPY --chown=disclaimr:disclaimr disclaimrweb ./disclaimrweb
COPY --chown=disclaimr:disclaimr disclaimrwebadmin ./disclaimrwebadmin
COPY --chown=disclaimr:disclaimr locale ./locale
# In-admin help docs (Markdown sources read by DocsView at request
# time). Cheap to ship — under 100 KiB total.
COPY --chown=disclaimr:disclaimr docs ./docs
# Editor libraries (see the assets stage); collectstatic serves them.
COPY --from=assets --chown=disclaimr:disclaimr /vendor ./disclaimrwebadmin/static/disclaimrwebadmin/vendor
COPY --chown=disclaimr:disclaimr manage.py disclaimr.py pyproject.toml ./
COPY --chown=disclaimr:disclaimr docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# ``compilemessages`` needs gettext to turn .po into the binary .mo
# files Django actually reads at runtime. Install gettext, build,
# then drop the apt cache to keep the layer slim.
RUN apt-get update && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R disclaimr:disclaimr /app

# Compile the .po translations to .mo so Django can load them at runtime.
# Django needs *some* settings to start, hence the throwaway env-vars.
RUN DJANGO_SECRET_KEY=build-time-only \
    DJANGO_DEBUG=False \
    DJANGO_ALLOWED_HOSTS=* \
    DATABASE_URL=sqlite:///:memory: \
    python manage.py compilemessages \
    && chown -R disclaimr:disclaimr /app/locale

USER disclaimr

EXPOSE 8000 5000

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["web"]
