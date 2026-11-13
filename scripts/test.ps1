<#
.SYNOPSIS
  Run all automated tests: backend (pytest), frontend unit (vitest), type-check, lint, and optionally E2E (Playwright).
.PARAMETER E2E
  Also run Playwright end-to-end tests (requires Shelfcraft running via scripts\start.ps1).
#>
param([switch]$E2E)
$Root = Split-Path -Parent $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
$failed = @()
Write-Host "==> Backend tests (pytest)" -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend"); & .\.venv\Scripts\python.exe -m pytest -q tests; if ($LASTEXITCODE) { $failed += "pytest" }; Pop-Location
Push-Location (Join-Path $Root "frontend")
Write-Host "==> Frontend type-check" -ForegroundColor Cyan; npx tsc --noEmit -p .; if ($LASTEXITCODE) { $failed += "tsc" }
Write-Host "==> Frontend lint" -ForegroundColor Cyan; npx eslint src; if ($LASTEXITCODE) { $failed += "eslint" }
Write-Host "==> Frontend unit tests (vitest)" -ForegroundColor Cyan; npx vitest run; if ($LASTEXITCODE) { $failed += "vitest" }
if ($E2E) { Write-Host "==> E2E (Playwright)" -ForegroundColor Cyan; npx playwright test; if ($LASTEXITCODE) { $failed += "playwright" } }
Pop-Location
if ($failed.Count) { Write-Host "FAILED: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
Write-Host "All test suites passed." -ForegroundColor Green
