$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $Here "server.py"

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Python) {
    throw "python.exe not found"
}
if (-not (Test-Path $Server)) {
    throw "server.py not found: $Server"
}

$SshHost = $env:DAFEIYU_SSH_HOST
$HostFile = Join-Path $HOME ".dafeiyu-admin\host"
if (-not $SshHost -and (Test-Path $HostFile)) {
    $SshHost = (Get-Content $HostFile -TotalCount 1).Trim()
}
if (-not $SshHost) {
    throw "SSH host not set. Use DAFEIYU_SSH_HOST=root@host or write it to $HostFile"
}
$OwnerQq = $env:DAFEIYU_OWNER_Telegram
$BotQq = $env:DAFEIYU_BOT_Telegram

Write-Host "Python: $Python"
Write-Host "Server: $Server"
Write-Host "Host:   $SshHost"
Write-Host "Owner Telegram env: $(if ($OwnerQq) { 'set' } else { 'not set' })"
Write-Host "Bot Telegram env:   $(if ($BotQq) { 'set' } else { 'not set' })"

$EnvArgs = @("--env", "DAFEIYU_SSH_HOST=$SshHost")
if ($OwnerQq) { $EnvArgs += @("--env", "DAFEIYU_OWNER_Telegram=$OwnerQq") }
if ($BotQq) { $EnvArgs += @("--env", "DAFEIYU_BOT_Telegram=$BotQq") }

# 幂等：先移除旧注册（不存在时忽略）
& claude mcp remove dafeiyu-admin 2>$null | Out-Null

& claude mcp add --scope user dafeiyu-admin @EnvArgs -- $Python $Server
if ($LASTEXITCODE -ne 0) {
    throw "claude mcp add failed, exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Registered. Open a new Claude Code session to load it. Current status:"
& claude mcp list
