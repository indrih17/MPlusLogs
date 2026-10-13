#ifndef AppVersion
  #define AppVersion "1.0.8"
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
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.StartupPageTitle=Choose when MPlusLogs Companion starts
english.StartupPageDescription=Make the helper available when you need to load logs.
english.StartupPageNote=You can change this later in Companion settings. The installer will also offer to open Companion when setup finishes.
english.StartupWindows=Start automatically when I sign in to Windows
english.StartupRetail=Start automatically with WoW Retail
english.StartupManual=Do not start automatically; I will open it myself
english.StartupRegistryWarning=Windows could not save the automatic start setting. Open MPlusLogs Companion settings to choose it manually.
english.UnsafeInstallDirectory=Choose a folder outside WoW Interface\AddOns. A running Companion in AddOns can prevent addon updates. The recommended location is %LOCALAPPDATA%\Programs\MPlusLogs Companion.
russian.StartupPageTitle=Когда запускать MPlusLogs Companion
russian.StartupPageDescription=Выберите, когда помощник должен быть готов к загрузке логов.
russian.StartupPageNote=Позже это можно изменить в настройках Companion. В конце установки также будет предложено открыть программу.
russian.StartupWindows=Запускать автоматически при входе в Windows
russian.StartupRetail=Запускать автоматически вместе с WoW Retail
russian.StartupManual=Не запускать автоматически — я буду открывать программу сам
russian.StartupRegistryWarning=Windows не сохранила настройку автозапуска. Выберите её вручную в настройках MPlusLogs Companion.
russian.UnsafeInstallDirectory=Выберите папку вне WoW Interface\AddOns. Запущенный Companion в AddOns мешает обновлению аддона. Рекомендуемая папка: %LOCALAPPDATA%\Programs\MPlusLogs Companion.

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
var
  StartupPage: TInputOptionWizardPage;

const
  StartupRunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  StartupWindowsName = 'MPlusLogs Companion';
  StartupRetailName = 'MPlusLogs Retail Launcher';

function WindowsCreateFile(Name: String; Access, Share: LongWord; Security: Integer;
  Creation, Flags: LongWord; Template: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function WindowsFinalPath(Handle: THandle; Buffer: String; Size, Flags: LongWord): LongWord;
  external 'GetFinalPathNameByHandleW@kernel32.dll stdcall';
function WindowsCloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function InAddOns(Path: String): Boolean;
begin
  Result := Pos('\interface\addons\', Lowercase(AddBackslash(Path))) > 0;
end;

function UnsafeInstallDirectory: Boolean;
var
  Path, Ancestor, Tail, Buffer, Parent: String;
  Handle: THandle;
  Size: LongWord;
begin
  Path := ExpandFileName(WizardDirValue);
  Result := InAddOns(Path);
  if Result then Exit;
  // Resolve the nearest existing ancestor to catch junctions and symlinks.
  Ancestor := Path;
  Tail := '';
  while not DirExists(Ancestor) do begin
    Parent := ExtractFileDir(Ancestor);
    if Parent = Ancestor then begin Result := True; Exit; end;
    Tail := ExtractFileName(Ancestor) + '\' + Tail;
    Ancestor := Parent;
  end;
  Handle := WindowsCreateFile(Ancestor, 0, 7, 0, 3, $02000000, 0);
  if Handle = THandle(-1) then begin Result := True; Exit; end;
  try
    SetLength(Buffer, 32768);
    Size := WindowsFinalPath(Handle, Buffer, 32768, 0);
    if (Size = 0) or (Size >= 32768) then begin Result := True; Exit; end;
    SetLength(Buffer, Size);
    Result := InAddOns(AddBackslash(Buffer) + Tail);
  finally
    WindowsCloseHandle(Handle);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (not WizardSilent) and (CurPageID = wpSelectDir) and UnsafeInstallDirectory then begin
    MsgBox(CustomMessage('UnsafeInstallDirectory'), mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  // /DIR and silent upgrades must follow the same rule as the wizard.
  if UnsafeInstallDirectory then
    Result := CustomMessage('UnsafeInstallDirectory');
end;

function StartupCommand(Mode: String): String;
begin
  // InitializeWizard runs before the app constant is initialized.
  // WizardDirValue respects the previous directory and the /DIR override.
  Result := '"' + AddBackslash(WizardDirValue) + 'MPlusLogs-Companion.exe" ' + Mode;
end;

function ExistingStartupChoice: Integer;
var
  Command: String;
begin
  if RegQueryStringValue(HKCU, StartupRunKey, StartupWindowsName, Command) and
     ((Command = StartupCommand('--background')) or
      (Command = AddBackslash(WizardDirValue) + 'MPlusLogs-Companion.exe --background')) then
    Result := 0
  else if RegQueryStringValue(HKCU, StartupRunKey, StartupRetailName, Command) and
          ((Command = StartupCommand('--watch-retail')) or
           (Command = AddBackslash(WizardDirValue) + 'MPlusLogs-Companion.exe --watch-retail')) then
    Result := 1
  else
    Result := 2;
end;

function RemoveStartupValue(ValueName: String): Boolean;
var
  ExistingValue: String;
begin
  if not RegQueryStringValue(HKCU, StartupRunKey, ValueName, ExistingValue) then
    Result := True
  else
    Result := RegDeleteValue(HKCU, StartupRunKey, ValueName);
end;

procedure InitializeWizard;
begin
  StartupPage := CreateInputOptionPage(wpSelectTasks,
    CustomMessage('StartupPageTitle'),
    CustomMessage('StartupPageDescription'),
    CustomMessage('StartupPageNote'), True, False);
  StartupPage.Add(CustomMessage('StartupWindows'));
  StartupPage.Add(CustomMessage('StartupRetail'));
  StartupPage.Add(CustomMessage('StartupManual'));
  StartupPage.SelectedValueIndex := ExistingStartupChoice;
end;

procedure ApplyStartupChoice;
var
  Ok: Boolean;
begin
  Ok := True;
  if StartupPage.SelectedValueIndex = 0 then begin
    Ok := RegWriteStringValue(HKCU, StartupRunKey, StartupWindowsName,
      StartupCommand('--background'));
    Ok := RemoveStartupValue(StartupRetailName) and Ok;
  end else if StartupPage.SelectedValueIndex = 1 then begin
    Ok := RegWriteStringValue(HKCU, StartupRunKey, StartupRetailName,
      StartupCommand('--watch-retail'));
    Ok := RemoveStartupValue(StartupWindowsName) and Ok;
  end else begin
    Ok := RemoveStartupValue(StartupWindowsName);
    Ok := RemoveStartupValue(StartupRetailName) and Ok;
  end;

  if not Ok then
    MsgBox(CustomMessage('StartupRegistryWarning'), mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (ExpandConstant('{param:UPDATECOMPANION|0}') <> '1') then
    ApplyStartupChoice;
end;

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
