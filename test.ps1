$ErrorActionPreference = 'Stop'
python -m unittest discover -s (Join-Path $PSScriptRoot 'outputs\hybrid') -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Controller tests failed.' }
