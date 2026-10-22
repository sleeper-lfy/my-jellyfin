; Build from the verified Windows onedir bundle; never package Linux binaries.
#ifndef AppVersion
  #define AppVersion "0.3.1"
#endif
#ifndef BundleDir
  #define BundleDir "..\dist\Lumen"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

[Setup]
AppId={{71850B7D-D7CF-4D25-80BC-8705FB77C116}
AppName=Lumen
AppVersion={#AppVersion}
AppPublisher=Lumen
AppPublisherURL=https://github.com/sleeper-lfy/my-jellyfin
DefaultDirName={localappdata}\Programs\Lumen
DefaultGroupName=Lumen
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=Lumen-Setup-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\Lumen.exe
VersionInfoVersion={#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Lumen"; Filename: "{app}\Lumen.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Lumen"; Filename: "{app}\Lumen.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Lumen.exe"; Description: "Launch Lumen"; Flags: nowait postinstall skipifsilent

; Deliberately no UninstallDelete entry: media and %LOCALAPPDATA%\Lumen belong to the user.
