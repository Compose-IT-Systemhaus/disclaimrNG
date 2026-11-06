# A plain Debian Postfix for the end-to-end test: accepts mail from anywhere, asks the
# disclaimrNG milter about every message and relays the result to the mail sink.
FROM debian:bookworm-slim

RUN echo "postfix postfix/main_mailer_type select Internet Site" | debconf-set-selections \
    && echo "postfix postfix/mailname string mx.planetexpress.test" | debconf-set-selections \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postfix \
    && rm -rf /var/lib/apt/lists/*

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 25
CMD ["/start.sh"]
