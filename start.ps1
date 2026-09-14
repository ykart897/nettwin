$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
$logDir = Join-Path $backend ".tmp"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend virtual environment is missing. Follow the README backend setup first."
}
if (-not $npmCommand) {
    throw "npm.cmd was not found in PATH."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    throw "Frontend dependencies are missing. Run npm install in frontend."
}

Push-Location $backend
try {
    if (Test-Path -LiteralPath (Join-Path $backend "nettwin.db")) {
        & $python -m scripts.backup_database | Write-Host
        if ($LASTEXITCODE -ne 0) { throw "Database backup failed; startup stopped before migration." }
    }
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
} finally {
    Pop-Location
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$serverHost = "127.0.0.1"

$openCellLine = Get-Content -LiteralPath (Join-Path $backend ".env") -ErrorAction SilentlyContinue |
    Where-Object { $_ -match "^OPENCELLID_CSV_PATH=" } |
    Select-Object -First 1
if ($openCellLine) {
    $openCellPath = ($openCellLine -split "=", 2)[1].Trim()
    if ($openCellPath -and -not (Test-Path -LiteralPath $openCellPath)) {
        Write-Warning "OpenCellID file is missing; that source will remain unconfigured."
    }
}

$backendListening = netstat -ano | Select-String ":8000\s"
if (-not $backendListening) {
    $backendProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("run.py", "--host", $serverHost, "--port", "8000") `
        -WorkingDirectory $backend `
        -RedirectStandardOutput (Join-Path $logDir "backend.out.log") `
        -RedirectStandardError (Join-Path $logDir "backend.err.log") `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "Backend started (PID $($backendProcess.Id))."
} else {
    Write-Host "Backend is already listening on port 8000."
}

$frontendListening = netstat -ano | Select-String ":5173\s"
if (-not $frontendListening) {
    $frontendProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory $frontend `
        -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") `
        -RedirectStandardError (Join-Path $logDir "frontend.err.log") `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "Frontend started (PID $($frontendProcess.Id))."
} else {
    Write-Host "Frontend is already listening on port 5173."
}

$healthy = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-RestMethod "http://127.0.0.1:8000/api/health/ready" -TimeoutSec 2
        if ($response.status -eq "ready") {
            $healthy = $true
            break
        }
    } catch {
        # The backend may still be starting.
    }
}

if (-not $healthy) {
    throw "Backend health check failed. See backend/.tmp/backend.err.log."
}

Write-Host "NetTwin is ready at http://127.0.0.1:5173"
