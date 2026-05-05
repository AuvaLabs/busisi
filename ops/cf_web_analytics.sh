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

: "${CF_API_TOKEN:?CF_API_TOKEN must be set (Account:Web Analytics:Edit)}"
: "${CF_ACCOUNT_ID:?CF_ACCOUNT_ID must be set}"

API="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json")

existing_json="$(curl -fsS "${AUTH[@]}" \
  "$API/accounts/$CF_ACCOUNT_ID/rum/site_info/list?per_page=100" || echo '{"result":[]}')"

existing_tag="$(echo "$existing_json" | python3 -c '
import json,sys
host = sys.argv[1]
data = json.load(sys.stdin)
for r in data.get("result", []) or []:
    if r.get("host") == host:
        print(r.get("site_tag",""))
        break
' "$HOST")"

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
import json,sys
d = json.load(sys.stdin)
if not d.get("success"):
    print("FAIL:", json.dumps(d.get("errors", []), indent=2))
    sys.exit(1)
r = d.get("result", {})
print(f"[cf-rum] registered site_tag={r.get(\"site_tag\")} ruleset_id={r.get(\"ruleset_id\")}")
'
