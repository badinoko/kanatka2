; Inno Setup Script for PhotoSelector
; Автоматический отбор фото с горнолыжной канатки

#define MyAppName "PhotoSelector"
#define MyAppVersion "1.0"
#define MyAppPublisher "Kanatka"
#define MyAppExeName "PhotoSelector.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installers
OutputBaseFilename=PhotoSelector_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main EXE and internal dependencies
Source: "..\dist\PhotoSelector\PhotoSelector.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\PhotoSelector\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; Batch helpers and docs
Source: "run_photoselector.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "process_folder.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\user_testing_guide.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion

[Dirs]
; Create working directories on install
Name: "{app}\workdir"
Name: "{app}\workdir\incoming"
Name: "{app}\workdir\selected"
Name: "{app}\workdir\sheets"
Name: "{app}\workdir\discarded"
Name: "{app}\workdir\rejected"
Name: "{app}\workdir\archive"
Name: "{app}\workdir\ambiguous"
Name: "{app}\workdir\logs"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
