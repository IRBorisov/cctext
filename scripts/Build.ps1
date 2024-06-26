Set-Location $PSScriptRoot\..

$packageName = 'cctext'
$output = "${PSScriptRoot}\..\dist"
$python = '.\venv\Scripts\python.exe'

if (-not (Test-Path -Path ${python} -PathType Leaf)) {
    & 'python' -m venv .\venv
    & ${python} -m pip install -r requirements-build.txt
}

if (Test-Path -Path ${output}) {
    Remove-Item ${output} -Recurse -Force
}

& ${python} -m build --no-isolation --outdir="${output}\"
$wheel = Get-Childitem -Path "${output}\*.whl" -Name
if (-not ${wheel}) {
    Write-Error "No wheel generated for ${packageName}"
    Exit 1
}

& ${python} -m pip install -I "${output}\${wheel}"
& ${python} -m unittest
$exitcode = $LASTEXITCODE
& ${python} -m pip uninstall -y ${packageName}
Exit ${exitcode}