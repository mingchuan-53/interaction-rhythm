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
$ManifestPath = Join-Path $ReleaseRoot "update.json"
$ManifestUrl = $env:INTERACTION_RHYTHM_UPDATE_URL
if ([string]::IsNullOrWhiteSpace($ManifestUrl)) {
  $ManifestUrl = "https://github.com/mingchuan-53/interaction-rhythm/releases/latest/download/update.json"
}

function Stop-ExistingApp {
  $names = @($AppExeName, $LegacyExeName, "TypeTracker")
  $processes = Get-Process -Name $names -ErrorAction SilentlyContinue
  if ($processes) {
    Write-Host "  正在停止运行中的旧版本..." -ForegroundColor DarkYellow
    $processes | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 700
  }
}

function Remove-TreeWithRetry([string]$Path) {
  if (-not (Test-Path $Path)) { return }
  $lastError = $null
  for ($i = 0; $i -lt 8; $i++) {
    try {
      Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
      return
    } catch {
      $lastError = $_
      Start-Sleep -Milliseconds (300 + $i * 200)
    }
  }
  throw $lastError
}

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
  --hidden-import webview `
  --hidden-import update_manager `
  --hidden-import settings `
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
Set-Content -LiteralPath "$BuildDir\update-url.txt" -Value $ManifestUrl -Encoding UTF8
Set-Content -LiteralPath "$BuildDir\data\update-url.txt" -Value $ManifestUrl -Encoding UTF8

$vbs = @(
  'Set WshShell = CreateObject("WScript.Shell")'
  'WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)'
  "WshShell.Run ""cmd /c $AppExeName.exe --background"", 0, False"
) -join "`r`n"
[System.IO.File]::WriteAllText("$BuildDir\StartHidden.vbs", $vbs, [System.Text.Encoding]::ASCII)

# [5/6] 发布到 current 和 releases
Write-Host "[5/6] 发布 current 和 releases..." -ForegroundColor Yellow
Stop-ExistingApp
Remove-TreeWithRetry $CurrentDir
Copy-Item -Path $BuildDir -Destination $CurrentDir -Recurse -Force

$releaseName = "$AppExeName-v$Version"
$releaseDir = Join-Path $ReleaseRoot $releaseName
Remove-TreeWithRetry $releaseDir
Copy-Item -Path $BuildDir -Destination $releaseDir -Recurse -Force

$legacyCleanDir = Join-Path $ReleaseRoot "$releaseName-clean"
$legacyCleanZip = Join-Path $ReleaseRoot "$releaseName-clean.zip"
foreach ($legacySharePath in @($legacyCleanDir, $legacyCleanZip)) {
  Remove-TreeWithRetry $legacySharePath
}

$shareDir = Join-Path $ReleaseRoot $AppDisplayName
Remove-TreeWithRetry $shareDir
Copy-Item -Path $BuildDir -Destination $shareDir -Recurse -Force
Remove-TreeWithRetry "$shareDir\data"
New-Item -Path "$shareDir\data\icons" -ItemType Directory -Force | Out-Null

$shareZip = Join-Path $ReleaseRoot "$AppDisplayName.zip"
if (Test-Path $shareZip) { Remove-Item -Force $shareZip }
Compress-Archive -Path "$shareDir\*" -DestinationPath $shareZip -CompressionLevel Optimal

$shareZipHash = (Get-FileHash -LiteralPath $shareZip -Algorithm SHA256).Hash.ToLowerInvariant()
$shareZipSize = (Get-Item -LiteralPath $shareZip).Length
$githubZip = Join-Path $ReleaseRoot "interaction-rhythm.zip"
if (Test-Path $githubZip) { Remove-Item -Force $githubZip }
Copy-Item -LiteralPath $shareZip -Destination $githubZip -Force
Remove-TreeWithRetry $shareDir
$downloadUrl = $env:INTERACTION_RHYTHM_DOWNLOAD_URL
if ([string]::IsNullOrWhiteSpace($downloadUrl)) {
  $downloadUrl = "https://github.com/mingchuan-53/interaction-rhythm/releases/download/v$Version/interaction-rhythm.zip"
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
    "启动后会轻量检查更新，有新版时给出提醒，不会自动安装。",
    "新增安装器脚本，可生成开始菜单、桌面快捷方式和卸载入口。",
    "默认更新通道改为 GitHub Release，减少手工配置遗漏。"
  )
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

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
Write-Host "  GitHub 发布包: dist\releases\interaction-rhythm.zip" -ForegroundColor Green
Write-Host "  更新清单: dist\releases\update.json" -ForegroundColor Green
Write-Host "  桌面快捷方式: $desktopPath\$AppDisplayName.lnk" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
