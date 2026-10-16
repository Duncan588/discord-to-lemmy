#!/bin/bash
# Log in as admin and print community counts + oldest posts via the Lemmy API.
set -euo pipefail; cd "$(dirname "$0")"
set -a; . ./.env; set +a
H=http://127.0.0.1:${LEMMY_PORT:-8536}
J=$(curl -s -XPOST $H/api/v3/user/login -H 'content-type: application/json' \
  -d "{\"username_or_email\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("jwt",""))')
[ -n "$J" ] && echo "admin login OK" || { echo "login failed"; exit 1; }
echo -n "anonymous access: "; curl -s "$H/api/v3/post/list?limit=1" | head -c 120; echo
curl -s -H "Authorization: Bearer $J" "$H/api/v3/community?name=$COMMUNITY_NAME" | python3 -c 'import json,sys;c=json.load(sys.stdin)["community_view"];print("community",c["community"]["name"],"posts",c["counts"]["posts"],"comments",c["counts"]["comments"])'
curl -s -H "Authorization: Bearer $J" "$H/api/v3/post/list?community_name=$COMMUNITY_NAME&sort=Old&limit=5" | python3 -c '
import json,sys
for p in json.load(sys.stdin)["posts"]: print(p["post"]["published"],p["creator"]["display_name"],p["counts"]["comments"],p["post"]["name"][:50])'
