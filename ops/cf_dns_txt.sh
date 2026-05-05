#!/usr/bin/env bash
# Cloudflare DNS TXT helper — upsert (idempotent) a TXT record on a zone.
#
# Use cases:
# 1. Google Search Console domain-property verification
#    (record name = the bare domain, value = google-site-verification=...)
# 2. Bing Webmaster Tools domain verification
# 3. Any other DNS-TXT challenge (postmark, resend, dmarc, etc.)
#
# Why this script: GSC + Bing both require a TXT record on the apex.
# Doing it via CF API (instead of the dashboard) means it's reproducible
# across V3+ zones in one shell line.
#
# Usage:
#   CF_API_TOKEN=xxx ops/cf_dns_txt.sh <zone_id> <name> <value>
#
# Examples:
#   ops/cf_dns_txt.sh 5136ef93965db0d6426c68e072baeb5a embedding.report \
#     'google-site-verification=AbCdEf1234567890'
#
# Idempotent: if a TXT record with the same name + value already exists,
# the call is a no-op. Set TXT_REPLACE_SAME_NAME=1 to overwrite the
# first existing TXT with the same name (use only when you know there's
# a single verification slot — DON'T use it for SPF/DMARC).
#
# Env:
#   CF_API_TOKEN — scoped token with Zone:DNS:Edit on the target zone.
#                  Tier-A — store in ~/kb_center/server_credentials.md,
#                  not in repo .env.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <zone_id> <name> <txt_value>" >&2
  exit 2
fi
ZONE="$1"
NAME="$2"
VALUE="$3"

: "${CF_API_TOKEN:?CF_API_TOKEN must be set (Zone:DNS:Edit scope)}"

API="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json")

existing_json="$(curl -fsS "${AUTH[@]}" \
  "$API/zones/$ZONE/dns_records?type=TXT&name=$NAME&per_page=100")"

already_id="$(echo "$existing_json" | python3 -c '
import json,sys
v = sys.argv[1]
data = json.load(sys.stdin)
for r in data.get("result", []):
    if r.get("content") == v:
        print(r.get("id"))
        break
' "$VALUE")"

if [ -n "$already_id" ]; then
  echo "[cf-dns-txt] $NAME -> already set ($already_id), no-op"
  exit 0
fi

update_id=""
if [ "${TXT_REPLACE_SAME_NAME:-0}" = "1" ]; then
  update_id="$(echo "$existing_json" | python3 -c '
import json,sys
data = json.load(sys.stdin)
for r in data.get("result", []):
    print(r.get("id"))
    break
')"
fi

body="$(python3 -c '
import json,sys
print(json.dumps({"type":"TXT","name":sys.argv[1],"content":sys.argv[2],"ttl":1,"proxied":False}))
' "$NAME" "$VALUE")"

if [ -n "$update_id" ]; then
  echo "[cf-dns-txt] $NAME -> updating $update_id"
  curl -fsS -X PUT "${AUTH[@]}" -d "$body" \
    "$API/zones/$ZONE/dns_records/$update_id" \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print("ok:",d["success"])'
else
  echo "[cf-dns-txt] $NAME -> creating"
  curl -fsS -X POST "${AUTH[@]}" -d "$body" \
    "$API/zones/$ZONE/dns_records" \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print("ok:",d["success"])'
fi
