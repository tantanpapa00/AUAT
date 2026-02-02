param(
  [string]$path = "C:\autobot\data\역추세매매 현물 v0.4.txt",
  [string]$url  = "http://127.0.0.1:8000/api/pine/parse-inputs",
  [string]$out  = "C:\autobot\payload_ok.json"
)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[string]$code = [System.IO.File]::ReadAllText($path, $utf8NoBom)

$codeJson = ConvertTo-Json -InputObject $code -Compress
$payload  = '{"code":' + $codeJson + '}'

[System.IO.File]::WriteAllBytes($out, $utf8NoBom.GetBytes($payload))

curl.exe -s -X POST $url -H "Content-Type: application/json; charset=utf-8" --data-binary "@$out"
