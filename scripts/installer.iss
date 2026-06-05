; Inno Setup script for Bandcamp Auto Uploader
; Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
; Version is pulled from scripts/version.inc (auto-generated from
; bandcamp_auto_uploader/__version__.py via scripts/set_version.py).

#include "version.inc"

#define MyAppName "Bandcamp Auto Uploader"
#define MyAppPublisher "Nai64"
#define MyAppURL "https://github.com/Nai64/bandcamp-auto-uploader"
#define MyAppExeName "Bandcamp Auto Uploader.exe"
; Source path of the EXE — set by build_gui.py per architecture.
; Default points to dist/x64/; override via scripts/installer.iss override or
; by passing /DMyAppSourcePath="..\dist\<arch>\{#MyAppExeName}" to ISCC.
#ifndef MyAppSourcePath
  #define MyAppSourcePath "..\dist\x64\{#MyAppExeName}"
#endif
#ifndef MyAppArch
  #define MyAppArch "x64"
#endif

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
OutputDir=..\dist\installer\{#MyAppArch}
OutputBaseFilename=BandcampAutoUploader-Setup-{#MyAppVersion}-{#MyAppArch}
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
Source: "{#MyAppSourcePath}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PRIVACY_POLICY.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent
