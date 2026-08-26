$ErrorActionPreference = "Stop"

Write-Host "=== AutoSellerAI final local deployment ===" -ForegroundColor Cyan

if (-not (Test-Path ".git")) {
    throw "프로젝트 루트에서 실행하세요. (.git을 찾을 수 없습니다)"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI를 찾을 수 없습니다. Docker Desktop을 먼저 실행하세요."
}

if (-not (Test-Path ".env")) {
    Write-Warning ".env 파일이 없습니다. API 연동은 동작하지 않을 수 있습니다."
}

Write-Host "[1/7] main 브랜치 동기화"
git switch main
git pull --ff-only origin main

Write-Host "[2/7] Docker Compose 구성 검증"
docker compose config --quiet

Write-Host "[3/7] 기존 서비스 정지"
docker compose down

Write-Host "[4/7] 최신 이미지 빌드"
docker compose build --pull

Write-Host "[5/7] 전체 서비스 기동"
docker compose up -d --force-recreate

Write-Host "[6/7] 서비스 상태 대기"
$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 5
    $ps = docker compose ps --format json | Out-String
    $sellerOk = $false
    $apiOk = $false
    $socialOk = $false
    try {
        $sellerOk = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://localhost:8501/_stcore/health").StatusCode -eq 200
    } catch {}
    try {
        $apiOk = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://localhost:8001/health").StatusCode -eq 200
    } catch {}
    try {
        $socialOk = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://localhost:8000/health").StatusCode -eq 200
    } catch {}
    $redisOk = ((docker compose exec -T redis redis-cli ping 2>$null) -match "PONG")
    if ($sellerOk -and $apiOk -and $socialOk -and $redisOk) { break }
} while ((Get-Date) -lt $deadline)

if (-not ($sellerOk -and $apiOk -and $socialOk -and $redisOk)) {
    docker compose ps
    docker compose logs --tail=120 autoseller seller-api social-api seller-worker seller-dangerous-worker seller-scheduler redis
    throw "배포 후 health check가 모두 통과하지 못했습니다. 위 로그를 확인하세요."
}

Write-Host "[7/7] 최종 상태"
docker compose ps

Write-Host "" 
Write-Host "배포 완료" -ForegroundColor Green
Write-Host "Seller OS:   http://localhost:8501"
Write-Host "Seller API:  http://localhost:8001/health"
Write-Host "Social API:  http://localhost:8000/health"
Write-Host "" 
Write-Host "운영 로그: docker compose logs -f seller-worker seller-dangerous-worker seller-scheduler" -ForegroundColor Yellow
