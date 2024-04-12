# Run lint
function RunLinters() {
  $pylint = "${PSScriptRoot}\..\venv\Scripts\pylint.exe"
  $mypy = "${PSScriptRoot}\..\venv\Scripts\mypy.exe"

  & $pylint cctext
  & $mypy cctext
}

RunLinters