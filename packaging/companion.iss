#ifndef AppVersion
  #define AppVersion "0.5.3"
#endif

[Setup]
AppId={{56DACDC3-C255-49E6-B6B0-045294B4D923}
AppName=MPlusLogs Companion
AppVersion={#AppVersion}
AppPublisher=indrih
AppPublisherURL=https://github.com/indrih17/MPlusLogs
DefaultDirName={localappdata}\Programs\MPlusLogs Companion
DefaultGroupName=MPlusLogs Companion
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release-output
OutputBaseFilename=MPlusLogs-Companion-{#AppVersion}-Setup
SetupIconFile=..\tools\assets\mpluslogs.ico
UninstallDisplayIcon={app}\MPlusLogs-Companion.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\MPlusLogs-Companion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\packaging\COMPANION-README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MPlusLogs Companion"; Filename: "{app}\MPlusLogs-Companion.exe"
Name: "{autodesktop}\MPlusLogs Companion"; Filename: "{app}\MPlusLogs-Companion.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MPlusLogs-Companion.exe"; Description: "{cm:LaunchProgram,MPlusLogs Companion}"; Flags: nowait postinstall skipifsilent

[Code]
procedure RemoveOwnStartup(ValueName, Mode: String);
var
  Command: String;
begin
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', ValueName, Command) then
    if (Command = '"' + ExpandConstant('{app}\MPlusLogs-Companion.exe') + '" ' + Mode) or
       (Command = ExpandConstant('{app}\MPlusLogs-Companion.exe') + ' ' + Mode) then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', ValueName);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then begin
    RemoveOwnStartup('MPlusLogs Companion', '--background');
    RemoveOwnStartup('MPlusLogs Retail Launcher', '--watch-retail');
  end;
end;
