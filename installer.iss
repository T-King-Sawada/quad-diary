; Inno Setup 6 script: wraps the PyInstaller onedir build (dist\QuadDiary\) into dist\QuadDiary-Setup.exe.
; Built by build.bat (ISCC /DMyAppVersion=x.y.z installer.iss).
; Per-user install (no admin): %LOCALAPPDATA%\Programs\QuadDiary. User data stays in %APPDATA%\QuadDiary.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "QuadDiary"
#define MyAppExeName "QuadDiary.exe"
#define MyAppURL "https://github.com/T-King-Sawada/quad-diary"
; Same value name as app/autostart.py APP_NAME
#define RunValueName "DailyDiary"

[Setup]
; Never change AppId: upgrades and uninstall are keyed on it.
AppId={{71E0B8D0-8558-4F46-B3C2-78D8975048C8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=T-King-Sawada
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=dist
OutputBaseFilename=QuadDiary-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
; Close a running QuadDiary (tray app) before overwriting its files
CloseApplications=force
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Drop libraries of the previous version so old and new DLLs never mix
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\QuadDiary\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Optional admin defaults: put config.default.json next to QuadDiary-Setup.exe
Source: "{src}\config.default.json"; DestDir: "{app}"; Flags: external skipifsourcedoesntexist onlyifdoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--show"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--show"; Tasks: desktopicon

[Run]
; Interactive install: optional "launch" checkbox on the last page
Filename: "{app}\{#MyAppExeName}"; Parameters: "--show"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; Silent install (auto-update from app/updater.py): restart the app quietly
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "StopQuadDiary"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { The app writes this autostart entry itself, so the uninstaller must remove it }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#RunValueName}');
end;
