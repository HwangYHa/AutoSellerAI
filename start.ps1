$Root = $PSScriptRoot
Set-Location $Root

# venv activation
$activate = "$Root\venv\Scripts\Activate.ps1"
if (Test-Path $activate) {
    & $activate
}

# check streamlit installed
& python -c "import streamlit" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing requirements..."
    pip install -r requirements.txt
}

Write-Host ""
Write-Host "AutoSeller starting..."
Write-Host "Open http://localhost:8501 in your browser"
Write-Host ""

$streamlitExe = "$Root\venv\Scripts\streamlit.exe"
if (Test-Path $streamlitExe) {
    & $streamlitExe run gui/app.py --server.port 8501 --server.headless false
} else {
    streamlit run gui/app.py --server.port 8501 --server.headless false
}
