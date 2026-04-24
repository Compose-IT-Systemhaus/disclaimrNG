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
COPY --chown=disclaimr:disclaimr manage.py disclaimr.py pyproject.toml ./
COPY --chown=disclaimr:disclaimr docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R disclaimr:disclaimr /app

USER disclaimr

EXPOSE 8000 5000

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["web"]
