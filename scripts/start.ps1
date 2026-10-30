#Requires -Version 5.1
<#
.SYNOPSIS
    Start the whole Annocollector repo: DB check -> port check -> backend -> frontend.

.DESCRIPTION
    1. Reads the repo-root .env (Supabase credentials) and verifies the database
       accepts a real connection (SELECT 1 through asyncpg).
    2. Checks that the backend/frontend ports are free.
    3. Installs backend deps (uv sync) if the venv is missing/incomplete.
    4. Applies Alembic migrations, then starts uvicorn.
    5. Installs frontend deps (npm install) if node_modules is missing, then
       starts Next.js.
    6. Streams both logs to this terminal and prints a summary when both are up.

    Press Ctrl+C to stop everything.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1

.EXAMPLE
    # Skip the DB check and migrations (e.g. working on the UI only)
    .\scripts\start.ps1 -SkipDbCheck -SkipMigrate

.EXAMPLE
    # Free the ports automatically instead of aborting
    .\scripts\start.ps1 -Force
#>
[CmdletBinding()]
param(
    [int]$BePort = 8000,
    [int]$FePort = 3000,
    [switch]$SkipDbCheck,
    [switch]$SkipMigrate,
    [switch]$SkipInstall,
    [switch]$CheckOnly,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BeDir = Join-Path $Root "be"
$FeDir = Join-Path $Root "fe"
$Py = Join-Path $BeDir ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}
function Write-Ok([string]$Text) { Write-Host "  [ok]   $Text" -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host "  [warn] $Text" -ForegroundColor Yellow }
function Write-Fail([string]$Text) { Write-Host "  [fail] $Text" -ForegroundColor Red }

function Stop-Script([string]$Message) {
    Write-Fail $Message
    Write-Host ""
    exit 1
}

# ---------------------------------------------------------------- .env parsing
function Read-DotEnv([string]$Path) {
    $values = @{}
    if (-not (Test-Path $Path)) { return $values }

    foreach ($raw in Get-Content -Path $Path -Encoding UTF8) {
        $line = $raw.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { continue }

        $index = $line.IndexOf("=")
        if ($index -lt 1) { continue }

        $key = $line.Substring(0, $index).Trim()
        $value = $line.Substring($index + 1).Trim()

        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $values[$key] = $value
    }
    return $values
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMs = 5000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        return ($task.Wait($TimeoutMs) -and $client.Connected)
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

# ------------------------------------------------------------------ DB check
function Get-DatabaseTarget {
    if (-not (Test-Path $EnvFile)) {
        Stop-Script "Missing $EnvFile. Copy .env.example to .env and fill SUPABASE_PASSWORD."
    }

    $cfg = Read-DotEnv $EnvFile

    if ($cfg["DATABASE_URL"]) {
        $dsn = $cfg["DATABASE_URL"] -replace "\+asyncpg", ""
        $isSqlite = $dsn.StartsWith("sqlite")
        return [pscustomobject]@{
            Dsn      = $dsn
            IsSqlite = $isSqlite
            Ssl      = ($cfg["DB_SSL"] -ne "false")
            Source   = "DATABASE_URL"
        }
    }

    $hostName = $cfg["SUPABASE_HOST"]
    $user = $cfg["SUPABASE_USER"]
    $password = $cfg["SUPABASE_PASSWORD"]
    $database = if ($cfg["SUPABASE_DB"]) { $cfg["SUPABASE_DB"] } else { "postgres" }
    $port = if ($cfg["SUPABASE_PORT"]) { [int]$cfg["SUPABASE_PORT"] } else { 6543 }

    if (-not $hostName) {
        return [pscustomobject]@{ Dsn = $null; IsSqlite = $true; Ssl = $false; Source = "sqlite fallback" }
    }
    if (-not $user -or -not $password) {
        Stop-Script "SUPABASE_USER / SUPABASE_PASSWORD missing in .env."
    }
    if ($password -like "*YOUR-PASSWORD*") {
        Stop-Script "SUPABASE_PASSWORD in .env is still the placeholder [YOUR-PASSWORD]. Put the real database password there."
    }

    $encoded = [uri]::EscapeDataString($password)
    $dsn = "postgresql://{0}:{1}@{2}:{3}/{4}" -f $user, $encoded, $hostName, $port, $database

    return [pscustomobject]@{
        Dsn      = $dsn
        IsSqlite = $false
        Ssl      = ($cfg["DB_SSL"] -ne "false")
        Source   = "SUPABASE_* (.env)"
        Host     = $hostName
        Port     = $port
    }
}

$checkerCode = @'
import asyncio
import os
import sys

import asyncpg


async def main() -> None:
    url = os.environ['ANN_DB_URL']
    use_ssl = os.environ.get('ANN_DB_SSL') == '1'
    conn = await asyncpg.connect(
        dsn=url,
        timeout=10,
        ssl='require' if use_ssl else None,
        statement_cache_size=0,
    )
    try:
        value = await conn.fetchval('select 1')
        print(value)
    finally:
        await conn.close()


try:
    asyncio.run(main())
except Exception as exc:
    print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
    sys.exit(1)
'@

# ---------------------------------------------------------------- port checks
function Get-PortOwner([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if (-not $conn) { return $null }
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        return [pscustomobject]@{
            Port = $Port
            PID  = $conn.OwningProcess
            Name = if ($proc) { $proc.ProcessName } else { "unknown" }
        }
    }
    catch {
        return $null
    }
}

function Assert-PortFree([int]$Port, [string]$Label) {
    $owner = Get-PortOwner -Port $Port
    if (-not $owner) {
        Write-Ok "port $Port free ($Label)"
        return
    }

    $detail = "port $Port ($Label) is already used by $($owner.Name) (PID $($owner.PID))"
    if (-not $Force) {
        Stop-Script "$detail. Stop that process or rerun with -Force."
    }

    Write-Warn "$detail - killing it (-Force)"
    cmd.exe /c "taskkill /PID $($owner.PID) /T /F" | Out-Null
    Start-Sleep -Milliseconds 800
    if (Get-PortOwner -Port $Port) {
        Stop-Script "port $Port is still busy after -Force. Free it manually."
    }
    Write-Ok "port $Port freed"
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            # 127.0.0.1 + a generous timeout: "localhost" can fall back from
            # IPv6 to IPv4 and blow a 2s budget on some Windows setups.
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -lt 500) { return $true }
            Start-Sleep -Milliseconds 700
        }
        catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

function Stop-Tree($Process) {
    if ($null -eq $Process) { return }
    try {
        if (-not $Process.HasExited) {
            cmd.exe /c "taskkill /PID $($Process.Id) /T /F" | Out-Null
        }
    }
    catch {
        # process already gone
    }
}

# ---------------------------------------------------------------------- main
Write-Host "Annocollector launcher" -ForegroundColor Magenta
Write-Host "repo: $Root"

# 1. Database
Write-Step "Checking database connection"

if ($SkipDbCheck) {
    Write-Warn "skipped (-SkipDbCheck)"
}
else {
    $target = Get-DatabaseTarget

    if ($target.IsSqlite) {
        Write-Warn "no Supabase credentials - the backend will use local SQLite"
    }
    elseif (-not (Test-Path $Py)) {
        Write-Warn "backend venv not installed yet; doing a TCP check on $($target.Host):$($target.Port)"
        if (Test-TcpPort -HostName $target.Host -Port $target.Port) {
            Write-Ok "TCP reachable (full auth check after deps install)"
        }
        else {
            Stop-Script "cannot reach $($target.Host):$($target.Port). Check network/VPN and SUPABASE_HOST."
        }
    }
    else {
        $env:ANN_DB_URL = $target.Dsn
        $env:ANN_DB_SSL = if ($target.Ssl) { "1" } else { "0" }
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        & $Py -c $checkerCode
        $exitCode = $LASTEXITCODE
        $watch.Stop()
        Remove-Item Env:ANN_DB_URL -ErrorAction SilentlyContinue
        Remove-Item Env:ANN_DB_SSL -ErrorAction SilentlyContinue

        if ($exitCode -ne 0) {
            Stop-Script "database connection failed (source: $($target.Source)). See the error above."
        }
        Write-Ok ("connected via {0} in {1} ms" -f $target.Source, [int]$watch.ElapsedMilliseconds)
    }
}

# 2. Ports
Write-Step "Checking ports"
Assert-PortFree -Port $BePort -Label "backend"
Assert-PortFree -Port $FePort -Label "frontend"

if ($CheckOnly) {
    Write-Step "Checks passed"
    Write-Ok "database reachable and ports $BePort/$FePort are free"
    exit 0
}

# 3. Backend dependencies
Write-Step "Backend dependencies"
$beReady = Test-Path $Py
if ($beReady) {
    & $Py -c "import fastapi, uvicorn, sqlalchemy, alembic, asyncpg" *> $null
    if ($LASTEXITCODE -ne 0) { $beReady = $false }
}

if ($beReady) {
    Write-Ok "be/.venv ready"
}
elseif ($SkipInstall) {
    Stop-Script "be/.venv is missing packages and -SkipInstall was given."
}
else {
    Write-Host "  installing with uv sync..."
    Push-Location $BeDir
    try {
        & uv sync
        if ($LASTEXITCODE -ne 0) { Stop-Script "uv sync failed." }
    }
    finally {
        Pop-Location
    }
    Write-Ok "be/.venv installed"
}

# 4. Migrations
if (-not $SkipMigrate) {
    Write-Step "Applying Alembic migrations"
    Push-Location $BeDir
    try {
        & uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) { Stop-Script "alembic upgrade head failed." }
    }
    finally {
        Pop-Location
    }
    Write-Ok "schema up to date"
}
else {
    Write-Warn "migrations skipped (-SkipMigrate)"
}

# 5. Frontend dependencies
Write-Step "Frontend dependencies"
$feReady = Test-Path (Join-Path $FeDir "node_modules\next")
if ($feReady) {
    Write-Ok "fe/node_modules ready"
}
elseif ($SkipInstall) {
    Stop-Script "fe/node_modules is missing and -SkipInstall was given."
}
else {
    Write-Host "  installing with npm install..."
    Push-Location $FeDir
    try {
        & npm.cmd install
        $installCode = $LASTEXITCODE
        if (-not (Test-Path (Join-Path $FeDir "node_modules\next"))) {
            Stop-Script "npm install failed (exit $installCode)."
        }
        if ($installCode -ne 0) {
            Write-Warn "npm reported exit code $installCode but node_modules looks complete"
        }
    }
    finally {
        Pop-Location
    }
    Write-Ok "fe/node_modules installed"
}

# 6. Start both, streaming logs to this terminal
Write-Step "Starting backend on :$BePort"
$beProc = Start-Process -FilePath "uv" `
    -ArgumentList @("run", "uvicorn", "app.main:app", "--reload", "--port", "$BePort") `
    -WorkingDirectory $BeDir -NoNewWindow -PassThru

Write-Step "Starting frontend on :$FePort"
$feProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", "npm.cmd run dev -- --port $FePort") `
    -WorkingDirectory $FeDir -NoNewWindow -PassThru

try {
    $beUp = Wait-Http -Url "http://127.0.0.1:$BePort/api/v1/health" -TimeoutSeconds 90
    $feUp = Wait-Http -Url "http://127.0.0.1:$FePort" -TimeoutSeconds 90

    Write-Step "Result"
    if ($beUp) {
        Write-Ok "backend   http://localhost:$BePort  (docs: http://localhost:$BePort/docs)"
    }
    else {
        Write-Fail "backend did not answer on :$BePort within 90s"
    }
    if ($feUp) {
        Write-Ok "frontend  http://localhost:$FePort"
    }
    else {
        Write-Fail "frontend did not answer on :$FePort within 90s"
    }

    if ($beUp -and $feUp) {
        Write-Host ""
        Write-Host "Both services are running. Press Ctrl+C to stop them." -ForegroundColor Magenta
    }

    while (-not $beProc.HasExited -and -not $feProc.HasExited) {
        Start-Sleep -Seconds 1
    }

    if ($beProc.HasExited) {
        Write-Warn "backend exited (code $(if ($null -ne $beProc.ExitCode) { $beProc.ExitCode } else { 'n/a' }))"
    }
    if ($feProc.HasExited) {
        Write-Warn "frontend exited (code $(if ($null -ne $feProc.ExitCode) { $feProc.ExitCode } else { 'n/a' }))"
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping services..." -ForegroundColor Yellow
    Stop-Tree $feProc
    Stop-Tree $beProc
    Start-Sleep -Milliseconds 800

    # taskkill /T can miss children on some setups; the ports were free before
    # we started, so anything listening now belongs to this run.
    foreach ($port in @($BePort, $FePort)) {
        $owner = Get-PortOwner -Port $port
        if ($owner) {
            cmd.exe /c "taskkill /PID $($owner.PID) /T /F" | Out-Null
        }
    }
}
