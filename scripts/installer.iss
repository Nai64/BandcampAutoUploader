; Inno Setup script for Bandcamp Auto Uploader
; Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
; Version is pulled from scripts/version.inc (auto-generated from
; bandcamp_auto_uploader/__version__.py via scripts/set_version.py).
;
; The following defines are passed by scripts/build_gui.py per build:
;   MyAppArch         - target architecture (x64, x86, arm64)
;   MyAppOutputDir    - output directory relative to this .iss file
;                       (defaults to the standard version folder)
;   MyAppExePath      - full path (relative to this .iss file) of the
;                       standalone EXE to wrap

#include "version.inc"

#define MyAppName "Bandcamp Auto Uploader"
#define MyAppPublisher "Nai64"
#define MyAppURL "https://github.com/Nai64/bandcamp-auto-uploader"
#define MyAppExeName "Bandcamp Auto Uploader.exe"
#ifndef MyAppArch
  #define MyAppArch "x64"
#endif
#ifndef MyAppOutputDir
  #define MyAppOutputDir "..\dist\BandcampAutoUploader-V{#MyAppVersion}"
#endif
#ifndef MyAppExePath
  #define MyAppExePath "{#MyAppOutputDir}\{#MyAppExeName}"
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
OutputDir={#MyAppOutputDir}
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
Source: "{#MyAppExePath}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PRIVACY_POLICY.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent
