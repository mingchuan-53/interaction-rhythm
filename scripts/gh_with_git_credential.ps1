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

$credPath = Join-Path $env:TEMP ("gh-git-credential-" + [System.Guid]::NewGuid().ToString("N") + ".txt")
try {
  [System.IO.File]::WriteAllText($credPath, "protocol=https`nhost=github.com`n`n", [System.Text.Encoding]::ASCII)
  $credential = cmd /c "git credential fill < `"$credPath`""
  $tokenLine = $credential | Where-Object { $_ -like "password=*" } | Select-Object -First 1
  $token = $tokenLine -replace "^password=", ""
  if ([string]::IsNullOrWhiteSpace($token)) {
    throw "No GitHub token available from Git Credential Manager. Run git push or gh auth login first."
  }
} finally {
  Remove-Item -LiteralPath $credPath -Force -ErrorAction SilentlyContinue
}

$env:GH_TOKEN = $token
& $GhPath @GhArgs
exit $LASTEXITCODE
