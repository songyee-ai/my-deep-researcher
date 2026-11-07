param([int]$Port = 8785)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Run .\setup.ps1 first.'
}
& .\.venv\Scripts\python.exe (Join-Path $PSScriptRoot 'server.py') --port $Port
