; Inno Setup script for Bandcamp Auto Uploader
; Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php)

#define MyAppName "Bandcamp Auto Uploader"
#define MyAppVersion "2.0"
#define MyAppPublisher "Nai64"
#define MyAppURL "https://github.com/Nai64/bandcamp-auto-uploader"
#define MyAppExeName "Bandcamp Auto Uploader.exe"

[Setup]
AppId={{B5A8C4D2-1F3E-4A7B-9C6D-8E2F1A3B5C7D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist\installer
OutputBaseFilename=BandcampAutoUploader-Setup-{#MyAppVersion}
SetupIconFile=..\bandcamp_auto_uploader\img\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PRIVACY_POLICY.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent
