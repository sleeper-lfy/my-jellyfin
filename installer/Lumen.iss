; Build from the verified Windows onedir bundle; never package Linux binaries.
#ifndef AppVersion
  #define AppVersion "0.4.14"
#endif
#ifndef BundleDir
  #define BundleDir "..\dist\Lumen"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

[Setup]
; Verification uses an isolated uninstall key; ordinary installs keep the stable AppId.
AppId={{71850B7D-D7CF-4D25-80BC-8705FB77C116}{param:LumenVerification|}
UsePreviousLanguage=no
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
SetupIconFile=..\assets\lumen.ico
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

[Code]
function IsThisInstallationStartup(const Command: String): Boolean;
var
  Application, Prefix: String;
begin
  { Match only the fixed command written by lumen.startup. An isolated
    /LumenVerification install must not remove the real installation's value. }
  Application := ExpandConstant('{app}\Lumen.exe');
  Prefix := '"' + Application + '" --background --data-dir ';
  Result := (Length(Command) > Length(Prefix)) and
    (CompareText(Copy(Command, 1, Length(Prefix)), Prefix) = 0);
  if not Result then
  begin
    { list2cmdline leaves an executable without spaces unquoted. }
    if Pos(' ', Application) = 0 then
    begin
      Prefix := Application + ' --background --data-dir ';
      Result := (Length(Command) > Length(Prefix)) and
        (CompareText(Copy(Command, 1, Length(Prefix)), Prefix) = 0);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Lumen', Command) then
    begin
      if IsThisInstallationStartup(Command) then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Lumen');
    end;
  end;
end;
