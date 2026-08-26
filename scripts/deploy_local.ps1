$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

Write-Host "=== AutoSellerAI local deployment ===" -ForegroundColor Cyan

if (-not (Test-Path ".git")) {
    throw "Run this script from the AutoSellerAI repository root."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Start Docker Desktop first."
}

if (-not (Test-Path ".env")) {
    Write-Warning ".env was not found. External API integrations may not work."
}

Write-Host "[1/7] Sync main branch"
& git switch main
if ($LASTEXITCODE -ne 0) { throw "git switch main failed." }
& git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw "git pull failed." }

Write-Host "[2/7] Validate Docker Compose configuration"
& docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed." }

Write-Host "[3/7] Stop existing services"
& docker compose down
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed." }

Write-Host "[4/7] Build latest images"
& docker compose build --pull
if ($LASTEXITCODE -ne 0) { throw "docker compose build failed." }

Write-Host "[5/7] Start all services"
& docker compose up -d --force-recreate
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

Write-Host "[6/7] Wait for service health"
$deadline = (Get-Date).AddMinutes(3)
$sellerOk = $false
$apiOk = $false
$socialOk = $false
$redisOk = $false

do {
    Start-Sleep -Seconds 5

    try {
        $sellerResponse = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "http://localhost:8501/_stcore/health"
        $sellerOk = ($sellerResponse.StatusCode -eq 200)
    }
    catch {
        $sellerOk = $false
    }

    try {
        $apiResponse = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "http://localhost:8001/health"
        $apiOk = ($apiResponse.StatusCode -eq 200)
    }
    catch {
        $apiOk = $false
    }

    try {
        $socialResponse = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "http://localhost:8000/health"
        $socialOk = ($socialResponse.StatusCode -eq 200)
    }
    catch {
        $socialOk = $false
    }

    try {
        $redisPing = (& docker compose exec -T redis redis-cli ping 2>$null | Out-String).Trim()
        $redisOk = ($redisPing -match "PONG")
    }
    catch {
        $redisOk = $false
    }

    Write-Host ("health seller={0} api={1} social={2} redis={3}" -f $sellerOk, $apiOk, $socialOk, $redisOk)

    if ($sellerOk -and $apiOk -and $socialOk -and $redisOk) {
        break
    }
}
while ((Get-Date) -lt $deadline)

if (-not ($sellerOk -and $apiOk -and $socialOk -and $redisOk)) {
    Write-Host "Deployment health check failed." -ForegroundColor Red
    & docker compose ps
    & docker compose logs --tail=120 autoseller seller-api social-api seller-worker seller-dangerous-worker seller-scheduler redis
    throw "One or more required services failed health checks."
}

Write-Host "[7/7] Final service status"
& docker compose ps

Write-Host ""
Write-Host "Deployment completed." -ForegroundColor Green
Write-Host "Seller OS:  http://localhost:8501"
Write-Host "Seller API: http://localhost:8001/health"
Write-Host "Social API: http://localhost:8000/health"
Write-Host ""
Write-Host "Logs: docker compose logs -f seller-worker seller-dangerous-worker seller-scheduler" -ForegroundColor Yellow
