#!/bin/sh
# Configure Postfix at start and run it in the foreground. Test setup only: it relays for
# every client, so never expose this container.
set -eu

postconf -e "myhostname = mx.planetexpress.test"
postconf -e "inet_interfaces = all"
postconf -e "inet_protocols = ipv4"
postconf -e "mynetworks = 0.0.0.0/0"
# Hand everything to the sink; the destination domains are not local.
postconf -e "relayhost = [mailpit]:1025"
postconf -e "smtp_tls_security_level = none"
# The disclaimrNG milter. tempfail: if it breaks, the test must see it instead of an unsigned mail.
postconf -e "smtpd_milters = inet:milter:5000"
postconf -e "non_smtpd_milters = inet:milter:5000"
postconf -e "milter_default_action = tempfail"
postconf -e "milter_protocol = 6"
# No chroot: names such as "milter" and "mailpit" resolve through Docker's DNS.
postconf -F '*/*/chroot = n'

exec postfix start-fg
