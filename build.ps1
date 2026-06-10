# 交互节律打包脚本 (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppExeName = "InteractionRhythm"
$AppDisplayName = "交互节律"
$LegacyExeName = "TypeTracker"
$PythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$PyInstallerExe = Join-Path $PSScriptRoot ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PythonExe)) {
  Write-Host "[0/6] 创建构建虚拟环境..." -ForegroundColor Yellow
  $SystemPython = (Get-Command python -ErrorAction Stop).Source
  & $SystemPython -m venv .venv
}
& $PythonExe -m pip install -r requirements.txt | Out-Host
if (-not (Test-Path $PyInstallerExe)) {
  & $PythonExe -m pip install "pyinstaller>=6.0" | Out-Host
}
$Version = & $PythonExe -c "import config; print(config.APP_VERSION)"
$DistRoot = Join-Path $PSScriptRoot "dist"
$BuildRoot = Join-Path $DistRoot "build"
$CurrentRoot = Join-Path $DistRoot "current"
$ReleaseRoot = Join-Path $DistRoot "releases"
$ArchiveRoot = Join-Path $DistRoot "archive"
$BuildDir = Join-Path $BuildRoot $AppExeName
$CurrentDir = Join-Path $CurrentRoot $AppExeName
$BackupDataDir = Join-Path $PSScriptRoot ".build-data-backup"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  交互节律 v$Version 打包脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# [1/6] 准备目录
Write-Host "[1/6] 准备目录..." -ForegroundColor Yellow
foreach ($dir in @($BuildRoot, $CurrentRoot, $ReleaseRoot, $ArchiveRoot)) {
  New-Item -Path $dir -ItemType Directory -Force | Out-Null
}
if (Test-Path $BackupDataDir) { Remove-Item -Recurse -Force $BackupDataDir }

$candidateDataDirs = @(
  (Join-Path $CurrentDir "data"),
  (Join-Path $BuildDir "data"),
  (Join-Path $DistRoot "$AppExeName\data"),
  (Join-Path $DistRoot "$LegacyExeName\data")
)
foreach ($candidate in $candidateDataDirs) {
  if (Test-Path $candidate) {
    Copy-Item -Path $candidate -Destination $BackupDataDir -Recurse -Force
    Write-Host "  已临时备份运行数据: $candidate" -ForegroundColor DarkGreen
    break
  }
}

if (Test-Path $BuildRoot) { Remove-Item -Recurse -Force $BuildRoot; New-Item -Path $BuildRoot -ItemType Directory -Force | Out-Null }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
foreach ($spec in @("$AppExeName.spec", "$LegacyExeName.spec", "TypeTracker.spec")) {
  if (Test-Path $spec) { Remove-Item -Force $spec }
}
if (Test-Path "app.ico") { Remove-Item -Force "app.ico" }

# [2/6] 生成图标
Write-Host "[2/6] 生成应用图标..." -ForegroundColor Yellow
& $PythonExe -c "from tray import make_ico; make_ico('app.ico')"
if ($LASTEXITCODE -ne 0) { Write-Host "图标生成失败！" -ForegroundColor Red; exit 1 }

# [3/6] PyInstaller 打包
Write-Host "[3/6] 使用 PyInstaller 打包..." -ForegroundColor Yellow
& $PyInstallerExe `
  --noconfirm `
  --onedir `
  --distpath $BuildRoot `
  --workpath build `
  --name $AppExeName `
  --icon app.ico `
  --add-data "static;static" `
  --hidden-import pynput.keyboard._win32 `
  --hidden-import pynput.mouse._win32 `
  --hidden-import pynput._util.win32 `
  --hidden-import webview `
  --hidden-import update_manager `
  --hidden-import clr `
  --hidden-import System `
  --exclude-module PIL.AvifImagePlugin `
  --exclude-module PIL.WebPImagePlugin `
  --exclude-module PIL.ImageCms `
  --exclude-module PIL.ImageQt `
  --exclude-module PIL.ImageTk `
  --exclude-module PIL.ImageDraw2 `
  --exclude-module PIL._avif `
  --exclude-module PIL._webp `
  --exclude-module PIL._imagingcms `
  --exclude-module PIL._imagingft `
  --exclude-module tkinter `
  --exclude-module numpy `
  --exclude-module pandas `
  --exclude-module scipy `
  --exclude-module matplotlib `
  --exclude-module IPython `
  --exclude-module pytest `
  --noconsole `
  main.py
if ($LASTEXITCODE -ne 0) { Write-Host "打包失败！" -ForegroundColor Red; exit 1 }

# [4/6] 写入运行数据和启动器
Write-Host "[4/6] 写入运行数据和启动器..." -ForegroundColor Yellow
New-Item -Path "$BuildDir\data" -ItemType Directory -Force | Out-Null
Copy-Item -Path "app.ico" -Destination "$BuildDir\$AppExeName.ico" -Force
Copy-Item -Path "app.ico" -Destination "$BuildDir\data\$AppDisplayName.ico" -Force
& $PythonExe -c "from tray import make_icon; make_icon(96).save(r'$BuildDir\data\interaction-rhythm-title.png', 'PNG')"
$includeData = $env:TYPETRACKER_INCLUDE_DATA -ne "0"
if ((Test-Path $BackupDataDir) -and $includeData) {
  Copy-Item -Path "$BackupDataDir\*" -Destination "$BuildDir\data" -Recurse -Force
  foreach ($legacyDataFile in @("TypeTracker.ico", "interaction-rhythm-title.png")) {
    $legacyDataPath = Join-Path "$BuildDir\data" $legacyDataFile
    if (Test-Path $legacyDataPath) { Remove-Item -Force $legacyDataPath }
  }
  Copy-Item -Path "app.ico" -Destination "$BuildDir\data\$AppDisplayName.ico" -Force
  & $PythonExe -c "from tray import make_icon; make_icon(96).save(r'$BuildDir\data\interaction-rhythm-title.png', 'PNG')"
  try {
    & $PythonExe -c "import sqlite3; p=r'dist\build\InteractionRhythm\data\tracker.db'; c=sqlite3.connect(p); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.execute('VACUUM'); c.close()"
  } catch {
    Write-Host "  数据库 WAL 清理跳过" -ForegroundColor DarkYellow
  }
  Write-Host "  已恢复运行数据" -ForegroundColor DarkGreen
} else {
  Write-Host "  已生成无历史数据构建" -ForegroundColor DarkGreen
}
if (Test-Path $BackupDataDir) { Remove-Item -Recurse -Force $BackupDataDir }

$vbs = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c $AppExeName.exe", 0, False
"@
[System.IO.File]::WriteAllText("$BuildDir\StartHidden.vbs", $vbs, [System.Text.Encoding]::ASCII)

# [5/6] 发布到 current 和 releases
Write-Host "[5/6] 发布 current 和 releases..." -ForegroundColor Yellow
if (Test-Path $CurrentDir) { Remove-Item -Recurse -Force $CurrentDir }
Copy-Item -Path $BuildDir -Destination $CurrentDir -Recurse -Force

$releaseName = "$AppExeName-v$Version"
$releaseDir = Join-Path $ReleaseRoot $releaseName
if (Test-Path $releaseDir) { Remove-Item -Recurse -Force $releaseDir }
Copy-Item -Path $BuildDir -Destination $releaseDir -Recurse -Force

$legacyCleanDir = Join-Path $ReleaseRoot "$releaseName-clean"
$legacyCleanZip = Join-Path $ReleaseRoot "$releaseName-clean.zip"
foreach ($legacySharePath in @($legacyCleanDir, $legacyCleanZip)) {
  if (Test-Path $legacySharePath) { Remove-Item -Recurse -Force $legacySharePath }
}

$shareDir = Join-Path $ReleaseRoot $AppDisplayName
if (Test-Path $shareDir) { Remove-Item -Recurse -Force $shareDir }
Copy-Item -Path $BuildDir -Destination $shareDir -Recurse -Force
if (Test-Path "$shareDir\data") { Remove-Item -Recurse -Force "$shareDir\data" }
New-Item -Path "$shareDir\data\icons" -ItemType Directory -Force | Out-Null

$shareZip = Join-Path $ReleaseRoot "$AppDisplayName.zip"
if (Test-Path $shareZip) { Remove-Item -Force $shareZip }
Compress-Archive -Path "$shareDir\*" -DestinationPath $shareZip -CompressionLevel Optimal

$shareZipHash = (Get-FileHash -LiteralPath $shareZip -Algorithm SHA256).Hash.ToLowerInvariant()
$shareZipSize = (Get-Item -LiteralPath $shareZip).Length
if (Test-Path $shareDir) { Remove-Item -Recurse -Force $shareDir }
$downloadUrl = $env:INTERACTION_RHYTHM_DOWNLOAD_URL
if ([string]::IsNullOrWhiteSpace($downloadUrl)) {
  $downloadUrl = (New-Object System.Uri($shareZip)).AbsoluteUri
}
$updateChannel = $env:INTERACTION_RHYTHM_UPDATE_CHANNEL
if ([string]::IsNullOrWhiteSpace($updateChannel)) { $updateChannel = "stable" }
$publishedAt = Get-Date -Format "yyyy-MM-dd"
$manifest = [ordered]@{
  app = $AppDisplayName
  channel = $updateChannel
  latest = $Version
  download_url = $downloadUrl
  sha256 = $shareZipHash
  size = $shareZipSize
  published_at = $publishedAt
  notes = @(
    "首页热力图调整为今天加前五天，保留居中留白，减少拥挤感。",
    "应用排行四周留白更舒适，窗口尺寸调整为 520×585。"
  )
}
$manifestPath = Join-Path $ReleaseRoot "update.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

# [6/6] 创建桌面快捷方式
Write-Host "[6/6] 创建桌面快捷方式..." -ForegroundColor Yellow
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell

foreach ($old in @("TypeTracker.lnk", "InteractionRhythm.lnk")) {
  $oldPath = Join-Path $desktopPath $old
  if (Test-Path $oldPath) {
    Move-Item -Path $oldPath -Destination (Join-Path $ArchiveRoot $old) -Force
  }
}

$shortcut = $shell.CreateShortcut((Join-Path $desktopPath "$AppDisplayName.lnk"))
$shortcut.TargetPath = "$CurrentDir\$AppExeName.exe"
$shortcut.WorkingDirectory = $CurrentDir
$shortcut.IconLocation = "$CurrentDir\$AppExeName.ico,0"
$shortcut.Description = "$AppDisplayName - 键鼠响应与应用节律"
$shortcut.Save()

try {
  $iconRefresh = Join-Path $env:windir "System32\ie4uinit.exe"
  if (Test-Path $iconRefresh) {
    Start-Process -FilePath $iconRefresh -ArgumentList "-show" -WindowStyle Hidden
  }
} catch {
  Write-Host "  Explorer 图标缓存刷新跳过，可手动刷新桌面" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  打包完成！" -ForegroundColor Green
Write-Host "  当前使用版: dist\current\$AppExeName\$AppExeName.exe" -ForegroundColor Green
Write-Host "  历史发布版: dist\releases\$releaseName\" -ForegroundColor Green
Write-Host "  朋友测试包: dist\releases\$AppDisplayName.zip" -ForegroundColor Green
Write-Host "  更新清单: dist\releases\update.json" -ForegroundColor Green
Write-Host "  桌面快捷方式: $desktopPath\$AppDisplayName.lnk" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
