param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$GhArgs
)

$ErrorActionPreference = "Stop"

$GhPath = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path -LiteralPath $GhPath)) {
  $command = Get-Command gh -ErrorAction SilentlyContinue
  if (-not $command) {
    throw "GitHub CLI not found. Install it with: winget install --id GitHub.cli -e"
  }
  $GhPath = $command.Source
}

$credential = "protocol=https`nhost=github.com`n`n" | git credential fill
$tokenLine = $credential | Where-Object { $_ -like "password=*" } | Select-Object -First 1
$token = $tokenLine -replace "^password=", ""
if ([string]::IsNullOrWhiteSpace($token)) {
  throw "No GitHub token available from Git Credential Manager. Run git push or gh auth login first."
}

$env:GH_TOKEN = $token
& $GhPath @GhArgs
exit $LASTEXITCODE
