; Inno Setup script for 交互节律
#define MyAppName "交互节律"
#define MyAppPublisher "明川"
#define MyAppURL "https://github.com/mingchuan-53/interaction-rhythm"
#define MyAppExeName "InteractionRhythm.exe"
#define MyAppVersion GetEnv("INTERACTION_RHYTHM_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "1.6"
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
DisableDirPage=yes
DisableProgramGroupPage=yes
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
Source: "..\dist\current\InteractionRhythm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\tracker.db,data\tracker.db-wal,data\tracker.db-shm,data\settings.json,data\icons\*,data\updates\*,startup-error.log,tray-error.log"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\InteractionRhythm.ico"
Name: "{group}\退出后台后启动"; Filename: "{app}\StartHidden.vbs"; WorkingDir: "{app}"; IconFilename: "{app}\InteractionRhythm.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\InteractionRhythm.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM InteractionRhythm.exe /F"; Flags: runhidden; RunOnceId: "KillInteractionRhythm"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/IM InteractionRhythm.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
