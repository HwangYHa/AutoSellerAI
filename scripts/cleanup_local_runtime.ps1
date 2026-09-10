$ErrorActionPreference = 'Stop'

Write-Host '=== AutoSellerAI local runtime cleanup ==='
Write-Host 'This removes only untracked runtime artifacts. It does NOT delete .env.'

# Remove accidental PowerShell-command filename if present.
Get-ChildItem -LiteralPath . -Force | Where-Object {
    $_.Name -like 's -ExecutionPolicy RemoteSigned*Activate.ps1*'
} | ForEach-Object {
    Write-Host "Removing accidental file: $($_.Name)"
    Remove-Item -LiteralPath $_.FullName -Force
}

# Remove generated media only. Keep the live SQLite DB itself.
if (Test-Path -LiteralPath 'data/generated') {
    Write-Host 'Removing generated media cache: data/generated'
    Remove-Item -LiteralPath 'data/generated' -Recurse -Force
}

Write-Host ''
Write-Host 'Remaining Git changes:'
git status --short
