#!/usr/bin/env bash
set -euo pipefail
BASE=${JOBHUB_API_URL:-http://localhost:8080}
login=$(curl -fsS -X POST "$BASE/api/v1/auth/demo-login" -H 'Content-Type: application/json' -d '{"email":"admin@jobhub.local","password":"password"}')
token=$(python -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])' <<< "$login")
me=$(curl -fsS "$BASE/api/v1/auth/me" -H "Authorization: Bearer $token")
admin=$(curl -fsS "$BASE/api/v1/admin/dataflow" -H "Authorization: Bearer $token")
seeker_login=$(curl -fsS -X POST "$BASE/api/v1/auth/demo-login" -H 'Content-Type: application/json' -d '{"email":"seeker@jobhub.local","password":"password"}')
seeker_token=$(python -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])' <<< "$seeker_login")
set +e
code=$(curl -s -o /tmp/jobhub-rbac.txt -w '%{http_code}' "$BASE/api/v1/admin/dataflow" -H "Authorization: Bearer $seeker_token")
set -e
[[ "$code" == "403" ]]
echo "SMOKE_TEST=PASS"
echo "ME=$me"
echo "ADMIN_DATAFLOW=$admin"
echo "SEEKER_ADMIN_STATUS=$code"
