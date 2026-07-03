param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$ScriptPath,

  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ScriptArgs
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$resolved = Resolve-Path -LiteralPath $ScriptPath
$source = Get-Content -Raw -Encoding UTF8 -LiteralPath $resolved.Path
$scriptDir = Split-Path -Parent $resolved.Path
$tempPath = Join-Path $scriptDir (".__utf8_bom_" + [System.IO.Path]::GetFileName($resolved.Path) + ".tmp.ps1")

try {
  Set-Content -LiteralPath $tempPath -Value $source -Encoding UTF8
  if ($ScriptArgs -and $ScriptArgs.Count -gt 0) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $tempPath @ScriptArgs
  } else {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $tempPath
  }
  exit $LASTEXITCODE
} finally {
  Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
}
