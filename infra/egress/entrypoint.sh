#!/bin/bash
set -Eeuo pipefail

install -d -m 0750 /var/log/squid /var/spool/squid
for log_name in access cache; do
  log_path="/var/log/squid/${log_name}.log"
  mkfifo -m 0600 "$log_path"
  tail -F "$log_path" &
  chown proxy:proxy "$log_path"
done
chmod 0755 /var/log/squid
chown proxy:proxy /var/spool/squid

exec /usr/sbin/squid -NYC -f /etc/squid/squid.conf
