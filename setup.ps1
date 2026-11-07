$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.cache\python'
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed.' }
}
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Ready. Run .\start.ps1, then open http://127.0.0.1:8785'
