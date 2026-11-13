<#
.SYNOPSIS
  Optional: install local CPU image generation (PyTorch CPU + diffusers) and pre-download SD-Turbo.
.DESCRIPTION
  Downloads ~250 MB of Python wheels and ~2.5 GB of model weights to data\models\hf.
  sd-turbo weights are under a Stability AI license — treat as personal/non-commercial until you
  verify the terms on https://huggingface.co/stabilityai/sd-turbo for your use.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run scripts\setup.ps1 first." }
Write-Host "Installing PyTorch (CPU) + diffusers..." -ForegroundColor Cyan
& $py -m pip install torch --index-url https://download.pytorch.org/whl/cpu
& $py -m pip install "diffusers>=0.31" "transformers>=4.46" accelerate safetensors
& $py -c "import torch" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Warning "torch could not load (missing VC++ runtime). Applying no-admin fallback."
  & $py -m pip install --quiet msvc-runtime
  Get-ChildItem (Join-Path $Root "backend\.venv\Scripts") -Include msvcp140*.dll,vcruntime140*.dll,concrt140.dll -Recurse |
    ForEach-Object { Copy-Item $_.FullName (Join-Path $Root "backend\.venv\Lib\site-packages\torch\lib") -Force }
}
Write-Host "Downloading SD-Turbo and running a benchmark (first run takes several minutes)..." -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend"); & $py scripts\bench_local_diffusion.py; Pop-Location
Write-Host "Done. Enable 'Local diffusion (CPU)' in Settings → AI providers (it is enabled automatically on a fresh install)." -ForegroundColor Green
