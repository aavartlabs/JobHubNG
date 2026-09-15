$ErrorActionPreference = 'Stop'
$base = if ($env:JOBHUB_API_URL) { $env:JOBHUB_API_URL } else { 'http://localhost:8080' }
$login = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/demo-login" -ContentType 'application/json' -Body '{"email":"admin@jobhub.local","password":"password"}'
$headers = @{ Authorization = "Bearer $($login.accessToken)" }
$me = Invoke-RestMethod -Uri "$base/api/v1/auth/me" -Headers $headers
$diag = Invoke-RestMethod -Uri "$base/api/v1/admin/dataflow" -Headers $headers
$seeker = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/demo-login" -ContentType 'application/json' -Body '{"email":"seeker@jobhub.local","password":"password"}'
try { Invoke-WebRequest -Uri "$base/api/v1/admin/dataflow" -Headers @{Authorization="Bearer $($seeker.accessToken)"} -UseBasicParsing | Out-Null; throw 'Expected HTTP 403' } catch { if ($_.Exception.Response.StatusCode.value__ -ne 403) { throw } }
Write-Host 'SMOKE_TEST=PASS'
$me | ConvertTo-Json -Depth 5
$diag | ConvertTo-Json -Depth 5
