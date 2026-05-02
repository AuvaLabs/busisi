#!/usr/bin/env bash
# Push heartbeat to status.auvalabs.com (Uptime Kuma).
# Activates only when UPTIME_PUSH_URL is set in /srv/grimoire/.env.
set -uo pipefail
URL=$(grep -E '^UPTIME_PUSH_URL=' /srv/grimoire/.env 2>/dev/null | cut -d= -f2-)
[ -z "$URL" ] && exit 0

load=$(awk '{print $1}' /proc/loadavg)
avail=$(free -m | awk '/^Mem/{print $7}')
healthy=$(awk -v l="$load" -v a="$avail" 'BEGIN{print (l<3.0 && a>1024)}')
if [ "$healthy" = "1" ]; then
  curl -sf -m 5 "$URL" >/dev/null
fi
