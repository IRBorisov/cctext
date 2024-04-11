Set-Location $PSScriptRoot\..

$python = '.\venv\Scripts\python.exe'
$env = '.\venv'
if (Test-Path -Path $python -PathType Leaf) {
    Remove-Item $env -Recurse -Force
}

& 'python' -m venv .\venv
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements-build.txt