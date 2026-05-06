#!/usr/bin/env bash
# Cloudflare Web Analytics — register a proxied zone for auto-tracking.
#
# Why: CF Web Analytics is privacy-first (no cookies, no fingerprinting),
# free, no CCPA/GDPR consent banner needed, and with auto_install=true
# CF injects the JS beacon on proxied responses with no template edit.
# This is the analytics layer for embedding.report / vested.news that
# replaces GA4-style tracking.
#
# Usage:
#   CF_API_TOKEN=xxx CF_ACCOUNT_ID=xxx \
#     ops/cf_web_analytics.sh <zone_id> <host>
#
# Examples:
#   ops/cf_web_analytics.sh 5136ef93965db0d6426c68e072baeb5a embedding.report
#   ops/cf_web_analytics.sh bc0f4e0e860a278b5db3692b86356120 vested.news
#
# Token scopes required:
#   Account:Web Analytics:Edit on the target account.
#
# Idempotent: if a site already exists for this host, the call is a
# no-op and the existing site_tag is printed.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <zone_id> <host>" >&2
  exit 2
fi
ZONE="$1"
HOST="$2"

: "${CF_ACCOUNT_ID:?CF_ACCOUNT_ID must be set}"

API="https://api.cloudflare.com/client/v4"
if [ -n "${CF_API_TOKEN:-}" ]; then
  AUTH=(-H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json")
elif [ -n "${CF_API_KEY:-}" ] && [ -n "${CF_API_EMAIL:-}" ]; then
  AUTH=(-H "X-Auth-Email: $CF_API_EMAIL" -H "X-Auth-Key: $CF_API_KEY" -H "Content-Type: application/json")
else
  echo "Set CF_API_TOKEN, or CF_API_KEY + CF_API_EMAIL." >&2
  exit 2
fi

# CF list endpoint returns site_tags but omits host/zone_tag at the top
# level — the binding lives under result[].ruleset.zone_tag. We fetch
# the list, then GET each site individually to find any whose ruleset
# is bound to the target zone.
list_json="$(curl -fsS "${AUTH[@]}" \
  "$API/accounts/$CF_ACCOUNT_ID/rum/site_info/list?per_page=100" || echo '{"result":[]}')"

site_tags="$(echo "$list_json" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for r in d.get("result") or []:
    print(r.get("site_tag",""))
')"

existing_tag=""
for st in $site_tags; do
  [ -z "$st" ] && continue
  detail="$(curl -fsS "${AUTH[@]}" \
    "$API/accounts/$CF_ACCOUNT_ID/rum/site_info/$st" || echo '{}')"
  hit="$(echo "$detail" | python3 -c '
import json, sys
zone = sys.argv[1]
d = (json.load(sys.stdin).get("result") or {})
rs = d.get("ruleset") or {}
if rs.get("zone_tag") == zone:
    print(d.get("site_tag",""))
' "$ZONE")"
  if [ -n "$hit" ]; then
    existing_tag="$hit"
    break
  fi
done

if [ -n "$existing_tag" ]; then
  echo "[cf-rum] $HOST -> already registered (site_tag=$existing_tag), no-op"
  exit 0
fi

body="$(python3 -c '
import json,sys
print(json.dumps({"auto_install": True, "host": sys.argv[1], "zone_tag": sys.argv[2]}))
' "$HOST" "$ZONE")"

resp="$(curl -fsS -X POST "${AUTH[@]}" -d "$body" \
  "$API/accounts/$CF_ACCOUNT_ID/rum/site_info")"

echo "$resp" | python3 -c '
import json, sys
d = json.load(sys.stdin)
if not d.get("success"):
    print("FAIL:", json.dumps(d.get("errors", []), indent=2))
    sys.exit(1)
r = d.get("result") or {}
rs = r.get("ruleset") or {}
print("[cf-rum] registered site_tag=" + (r.get("site_tag") or "?") + " zone=" + (rs.get("zone_name") or "?"))
'
