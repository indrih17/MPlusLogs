#ifndef AppVersion
  #define AppVersion "1.0.31"
#endif

[Setup]
AppId={{56DACDC3-C255-49E6-B6B0-045294B4D923}
AppName=MPlusLogs Companion
AppVersion={#AppVersion}
AppPublisher=indrih
AppPublisherURL=https://github.com/indrih17/MPlusLogs
DefaultDirName={localappdata}\Programs\MPlusLogs Companion
; A stale installation record can point inside AddOns after an addon update.
; Keep directory selection available so reinstall can repair that location.
DisableDirPage=no
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
; The opt-in Retail watcher has no window and cannot answer a graceful close.
; Limit forced closure to processes holding this installation's executable.
CloseApplications=force
CloseApplicationsFilter=MPlusLogs-Companion.exe
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
english.Notifications=Show popup notifications from MPlusLogs Companion
english.NotificationsGroup=Notifications:
english.NotificationsWarning=Could not save the notification setting. You can change it in MPlusLogs Companion settings.
english.UnsafeInstallDirectory=Do not install Companion inside an individual addon folder (for example AddOns\MPlusLogs). Choose AddOns itself, a separate Companion folder, or %LOCALAPPDATA%\Programs\MPlusLogs Companion.
russian.StartupPageTitle=Когда запускать MPlusLogs Companion
russian.StartupPageDescription=Выберите, когда MPlusLogs Companion должен быть готов к загрузке логов.
russian.StartupPageNote=Позже это можно изменить в настройках Companion. В конце установки также будет предложено открыть программу.
russian.StartupWindows=Запускать автоматически при входе в Windows
russian.StartupRetail=Запускать автоматически вместе с WoW Retail
russian.StartupManual=Не запускать автоматически — я буду открывать программу сам
russian.StartupRegistryWarning=Windows не сохранила настройку автозапуска. Выберите её вручную в настройках MPlusLogs Companion.
russian.Notifications=Показывать всплывающие уведомления MPlusLogs Companion
russian.NotificationsGroup=Уведомления:
russian.NotificationsWarning=Не удалось сохранить настройку уведомлений. Измените её в настройках MPlusLogs Companion.
russian.UnsafeInstallDirectory=Не устанавливайте Companion в папку отдельного аддона (например AddOns\MPlusLogs). Выберите саму папку AddOns, отдельную папку Companion или %LOCALAPPDATA%\Programs\MPlusLogs Companion.

[Tasks]
Name: "notifications"; Description: "{cm:Notifications}"; GroupDescription: "{cm:NotificationsGroup}"
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

function InAddonFolder(Path: String): Boolean;
var
  Marker, Tail, Folder: String;
  Index: Integer;
  Entry: TFindRec;
begin
  Result := False;
  Path := AddBackslash(Path);
  Marker := '\interface\addons\';
  Index := Pos(Marker, Lowercase(Path));
  if Index = 0 then Exit;
  Tail := Copy(Path, Index + Length(Marker), Length(Path));
  if Tail = '' then Exit; // AddOns itself is allowed.
  Folder := Copy(Tail, 1, Pos('\', Tail) - 1);
  // Our addon remains protected if an updater has already removed its TOC.
  if Lowercase(Folder) = 'mpluslogs' then begin Result := True; Exit; end;
  Folder := Copy(Path, 1, Index + Length(Marker) - 1) + Folder;
  if FindFirst(AddBackslash(Folder) + '*.toc', Entry) then begin
    try
      repeat
        if (Entry.Attributes and $10) = 0 then begin Result := True; Break; end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

function UnsafeInstallDirectory: Boolean;
var
  Path, Ancestor, Tail, Buffer, Parent: String;
  Handle: THandle;
  Size: LongWord;
begin
  Path := ExpandFileName(WizardDirValue);
  Result := InAddonFolder(Path);
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
    Result := InAddonFolder(AddBackslash(Buffer) + Tail);
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

procedure ApplyNotificationChoice;
var
  Choice: String;
  ExitCode: Integer;
begin
  if WizardIsTaskSelected('notifications') then Choice := 'on'
  else Choice := 'off';
  if not Exec(ExpandConstant('{app}\MPlusLogs-Companion.exe'),
      '--set-notifications ' + Choice, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
    MsgBox(CustomMessage('NotificationsWarning'), mbError, MB_OK);
  end else if ExitCode <> 0 then
    MsgBox(CustomMessage('NotificationsWarning'), mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (ExpandConstant('{param:UPDATECOMPANION|0}') <> '1') then begin
    ApplyStartupChoice;
    if not WizardSilent then ApplyNotificationChoice;
  end;
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
