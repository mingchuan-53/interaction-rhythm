; Inno Setup script for 扣舷
#define MyAppName "扣舷"
#define MyAppPublisher "明川"
#define MyAppURL "https://github.com/mingchuan-53/interaction-rhythm"
#define MyAppExeName "InteractionRhythm.exe"
#define MyAppVersion GetEnv("INTERACTION_RHYTHM_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "1.9.5"
#endif

[Setup]
AppId={{B91F0158-8F1E-4B2E-B0F0-7EA94EC0F10F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases/latest
DefaultDirName={localappdata}\Programs\InteractionRhythm
DefaultGroupName={#MyAppName}
DisableDirPage=auto
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=interaction-rhythm-setup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\dist\current\InteractionRhythm\InteractionRhythm.ico
UninstallDisplayIcon={app}\InteractionRhythm.ico
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
Source: "..\dist\current\InteractionRhythm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\tracker.db,data\tracker.db-wal,data\tracker.db-shm,data\settings.json,data\icons\*,data\updates\*,data\diagnostics\*,startup-error.log,tray-error.log"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\InteractionRhythm.ico"
Name: "{group}\退出后台后启动"; Filename: "{app}\StartHidden.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\InteractionRhythm.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\InteractionRhythm.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM InteractionRhythm.exe /F"; Flags: runhidden; RunOnceId: "KillInteractionRhythm"

[Code]
var
  PreviousInstallDir: String;

function TrimTrailingSlash(Value: String): String;
begin
  Result := Value;
  while (Length(Result) > 0) and (Copy(Result, Length(Result), 1) = '\') do
    Delete(Result, Length(Result), 1);
end;

function ReadPreviousInstallDir(var Dir: String): Boolean;
begin
  Result :=
    RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B91F0158-8F1E-4B2E-B0F0-7EA94EC0F10F}_is1', 'InstallLocation', Dir) or
    RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B91F0158-8F1E-4B2E-B0F0-7EA94EC0F10F}_is1', 'InstallLocation', Dir);
  if Result then
    Dir := TrimTrailingSlash(Dir);
  if (not Result) and DirExists(ExpandConstant('{localappdata}\Programs\InteractionRhythm')) then
  begin
    Dir := TrimTrailingSlash(ExpandConstant('{localappdata}\Programs\InteractionRhythm'));
    Result := True;
  end;
end;

procedure CopyDirMissingOnly(SourceDir, TargetDir: String);
var
  FindRec: TFindRec;
  SourcePath: String;
  TargetPath: String;
begin
  if not DirExists(SourceDir) then
    Exit;

  ForceDirectories(TargetDir);
  if FindFirst(SourceDir + '\*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          SourcePath := SourceDir + '\' + FindRec.Name;
          TargetPath := TargetDir + '\' + FindRec.Name;
          if DirExists(SourcePath) then
            CopyDirMissingOnly(SourcePath, TargetPath)
          else if not FileExists(TargetPath) then
            CopyFile(SourcePath, TargetPath, False);
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  ReadPreviousInstallDir(PreviousInstallDir);
  Exec('taskkill', '/IM InteractionRhythm.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

procedure InitializeWizard();
begin
  if (PreviousInstallDir <> '') and DirExists(PreviousInstallDir) then
    WizardForm.DirEdit.Text := PreviousInstallDir;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  NewInstallDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    NewInstallDir := TrimTrailingSlash(ExpandConstant('{app}'));
    if (PreviousInstallDir <> '') and DirExists(PreviousInstallDir + '\data') and
       (CompareText(PreviousInstallDir, NewInstallDir) <> 0) then
      CopyDirMissingOnly(PreviousInstallDir + '\data', NewInstallDir + '\data');
  end;
end;
