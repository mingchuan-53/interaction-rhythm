# 扣舷安装器构建脚本
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Version = & ".\.venv\Scripts\python.exe" -c "import config; print(config.APP_VERSION)"
$IsccCandidates = @(@(
  (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
  "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique)

if (-not $IsccCandidates) {
  Write-Host "没有找到 Inno Setup 6。请安装后重新运行 build-installer.ps1。" -ForegroundColor Yellow
  Write-Host "下载地址: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
  exit 2
}

$CurrentExe = Join-Path $PSScriptRoot "dist\current\InteractionRhythm\InteractionRhythm.exe"
if (-not (Test-Path $CurrentExe)) {
  Write-Host "没有找到 current 构建，先运行 .\build.ps1。" -ForegroundColor Yellow
  exit 1
}

$env:INTERACTION_RHYTHM_VERSION = $Version
$InstallerScript = Join-Path $PSScriptRoot "installer\interaction-rhythm.iss"
$InstallerName = "interaction-rhythm-setup-v$Version.exe"
$InstallerBaseName = [IO.Path]::GetFileNameWithoutExtension($InstallerName)
$TempInstallerBaseName = "$InstallerBaseName-build-$([DateTime]::Now.ToString('yyyyMMddHHmmss'))"
$ReleaseRoot = Join-Path $PSScriptRoot "dist\releases"
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null

& $IsccCandidates[0] "/O$ReleaseRoot" "/F$TempInstallerBaseName" $InstallerScript
if ($LASTEXITCODE -ne 0) {
  Write-Host "安装器构建失败。" -ForegroundColor Red
  exit $LASTEXITCODE
}

$TempInstallerPath = Join-Path $ReleaseRoot "$TempInstallerBaseName.exe"
$ReleaseInstallerPath = Join-Path $ReleaseRoot $InstallerName
Copy-Item -Force $TempInstallerPath $ReleaseInstallerPath
Remove-Item -Force $TempInstallerPath

$InstallerOutput = Join-Path $PSScriptRoot "installer\output"
New-Item -ItemType Directory -Force -Path $InstallerOutput | Out-Null
Copy-Item -Force $ReleaseInstallerPath (Join-Path $InstallerOutput $InstallerName)

Write-Host "安装器构建完成: dist\releases\$InstallerName" -ForegroundColor Green
Write-Host "已同步到: installer\output\$InstallerName" -ForegroundColor Green
