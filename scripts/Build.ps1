Set-Location $PSScriptRoot\..

$packageName = 'cctext'
$output = 'output'
$python = '.\venv\Scripts\python.exe'
if (-not (Test-Path -Path $python -PathType Leaf)) {
    & 'python' -m venv .\venv
    & $python -m pip install -r requirements.txt
    & $python -m pip install -r requirements-build.txt
}

if (Test-Path -Path $output\$packageName) {
    Remove-Item $output\$packageName -Recurse -Force
}

& $python -m build --outdir=$output\$packageName
$wheel = Get-Childitem -Path $output\$packageName\*.whl -Name
if (-not $wheel) {
    Write-Error "No wheel generated for $packageName"
    Exit 1
}

& $python -m pip install -I $output\$packageName\$wheel
& $python -m unittest
$exitcode = $LASTEXITCODE
& $python -m pip uninstall -y $packageName
Exit $exitcode