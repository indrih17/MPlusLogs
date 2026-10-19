"""Run the actual installer code with isolated registry values and destinations."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


def compiler():
    paths = [shutil.which("ISCC.exe"), os.environ.get("MPLUSLOGS_ISCC"),
             str(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Inno Setup 6/ISCC.exe"),
             str(Path(os.environ.get("LOCALAPPDATA", "")) / "MPlusLogsDevelopment/build-tools/inno/ISCC.exe")]
    return next((path for path in paths if path and Path(path).is_file()), None)


@unittest.skipUnless(sys.platform == "win32" and compiler(), "Requires Windows and Inno Setup compiler")
class InstallerTests(unittest.TestCase):
    def test_notification_checkbox_defaults_on_and_passes_explicit_choice(self):
        compiler_cs=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler_cs.is_file(): self.skipTest('Requires .NET Framework compiler')
        with tempfile.TemporaryDirectory(prefix='MPlusLogs-notification-install-') as temporary:
            base=Path(temporary)
            payload=base/'MPlusLogs-Companion.exe'
            code=base/'Fixture.cs'
            code.write_text('class Fixture { static void Main(string[] args) { '
                            'System.IO.File.WriteAllText(System.IO.Path.Combine('
                            'System.AppDomain.CurrentDomain.BaseDirectory,"notification-choice.txt"),'
                            'string.Join(" ",args)); } }')
            subprocess.run([str(compiler_cs),'/nologo','/target:winexe','/out:'+str(payload),str(code)],
                           check=True,capture_output=True)
            source=(ROOT/'packaging/companion.iss').read_text(encoding='utf-8')
            replacements={'AppId':'MPlusLogs-Notification-Test-'+uuid.uuid4().hex,
                          'OutputDir':str(base),'OutputBaseFilename':'TestSetup'}
            for name,value in replacements.items():
                source=re.sub(r'^'+name+r'=.*$',lambda m:name+'='+value,source,flags=re.M)
            source=source.replace('[Setup]','[Setup]\nUninstallable=no\nCreateUninstallRegKey=no\nUsePreviousTasks=no',1)
            source=re.sub(r'^SetupIconFile=.*\n','',source,flags=re.M)
            source=re.sub(r'\[Files\].*?\[Code\]',lambda m:'[Files]\nSource: "'+str(payload)+'"; DestDir: "{app}"\n[Code]',source,flags=re.S)
            # Exercise the real task selection and save code without displaying a wizard.
            # UPDATECOMPANION skips production postinstall actions; the test event calls only
            # the notification action against the isolated executable above.
            source += '''
<event('CurStepChanged')>
procedure VerifyNotificationChoice(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then ApplyNotificationChoice;
end;
'''
            script=base/'fixture.iss';script.write_text(source,encoding='utf-8')
            compiled=subprocess.run([compiler(),'/Q',str(script)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            for name,tasks,expected in [('default',None,'on'),('disabled','desktopicon','off'),('enabled','notifications','on')]:
                with self.subTest(choice=name):
                    destination=base/name
                    args=[str(base/'TestSetup.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',
                          '/UPDATECOMPANION=1','/DIR='+str(destination)]
                    if tasks is not None: args.append('/TASKS='+tasks)
                    result=subprocess.run(args,capture_output=True,timeout=30)
                    self.assertEqual(result.returncode,0)
                    self.assertEqual((destination/'notification-choice.txt').read_text(),'--set-notifications '+expected)

    def test_upgrade_closes_background_process_holding_companion_executable(self):
        compiler_cs=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler_cs.is_file(): self.skipTest('Requires .NET Framework compiler')
        with tempfile.TemporaryDirectory(prefix='MPlusLogs-background-upgrade-') as temporary:
            base=Path(temporary);target=base/'installed';target.mkdir()
            old=target/'MPlusLogs-Companion.exe'
            code=base/'Fixture.cs'
            code.write_text('using System.Reflection; [assembly: AssemblyVersion("1.0.0.0")] '
                            'class Fixture { static void Main() { System.Threading.Thread.Sleep(60000); } }')
            subprocess.run([str(compiler_cs),'/nologo','/target:winexe','/out:'+str(old),str(code)],check=True,capture_output=True)
            replacement=base/'MPlusLogs-Companion.exe'
            code.write_text('using System.Reflection; [assembly: AssemblyVersion("2.0.0.0")] '
                            'class Fixture { static void Main() {} }')
            subprocess.run([str(compiler_cs),'/nologo','/target:winexe','/out:'+str(replacement),str(code)],check=True,capture_output=True)
            source=(ROOT/'packaging/companion.iss').read_text(encoding='utf-8')
            app_id='MPlusLogs-Background-Upgrade-Test-'+uuid.uuid4().hex
            replacements={'AppId':app_id,'AppName':'MPlusLogs background upgrade fixture',
                          'DefaultDirName':str(target),'OutputDir':str(base),'OutputBaseFilename':'TestSetup',
                          'Uninstallable':'no'}
            for name,value in replacements.items():
                if re.search(r'^'+name+'=',source,re.M):
                    source=re.sub(r'^'+name+r'=.*$',lambda m:name+'='+value,source,flags=re.M)
                else: source=source.replace('[Setup]','[Setup]\n'+name+'='+value,1)
            source=re.sub(r'^SetupIconFile=.*\n','',source,flags=re.M)
            source=re.sub(r'\[Files\].*?\[Code\]',lambda m:'[Files]\nSource: "'+str(replacement)+'"; DestDir: "{app}"; Flags: ignoreversion\n[Code]',source,flags=re.S)
            source=source.replace('Software\\Microsoft\\Windows\\CurrentVersion\\Run','Software\\'+app_id)
            script=base/'fixture.iss';script.write_text(source,encoding='utf-8')
            compiled=subprocess.run([compiler(),'/Q',str(script)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            other_directory=base/'unrelated';other_directory.mkdir()
            other_executable=other_directory/old.name
            shutil.copy2(old,other_executable)
            other_process=subprocess.Popen([str(other_executable)],creationflags=subprocess.CREATE_NO_WINDOW)
            process=subprocess.Popen([str(old)],creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                import time
                time.sleep(0.2)
                with self.assertRaises(PermissionError): old.unlink()
                log=base/'upgrade.log'
                result=subprocess.run([str(base/'TestSetup.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES',
                    '/NORESTART','/NORESTARTAPPLICATIONS','/CLOSEAPPLICATIONS','/UPDATECOMPANION=1',
                    '/DIR='+str(target),'/LOG='+str(log)],capture_output=True,timeout=30)
                details=log.read_text(encoding='utf-8-sig',errors='replace')
                self.assertEqual(result.returncode,0,details)
                self.assertIsNotNone(process.poll(),'Background watcher still owns the installed executable')
                self.assertEqual(old.read_bytes(),replacement.read_bytes())
                self.assertIsNone(other_process.poll(),'Unrelated installation must keep running')
            finally:
                for child in (process,other_process):
                    if child.poll() is None:
                        child.kill();child.wait(timeout=10)

    def test_reinstall_can_change_directory_with_stale_uninstall_record(self):
        import winreg
        source = (ROOT / "packaging/companion.iss").read_text(encoding="utf-8")
        app_id = "MPlusLogs-Reinstall-Test-" + uuid.uuid4().hex
        startup_key = "Software\\" + app_id
        uninstall_key = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + app_id + "_is1"
        with tempfile.TemporaryDirectory(prefix="MPlusLogs-reinstall-test-") as temporary:
            base = Path(temporary)
            old = base / "WoW/Interface/AddOns/MPlusLogs/Companion"
            chosen = base / "Programs/Companion"
            payload = base / "fixture.txt"
            payload.write_text("isolated reinstall fixture")
            # Keep production Setup directives and code, including directory-page policy.
            source = re.sub(r"^AppId=.*$", "AppId=" + app_id, source, flags=re.M)
            for name, value in (("DefaultDirName", str(chosen)), ("OutputDir", str(base)),
                                ("OutputBaseFilename", "TestSetup")):
                source = re.sub(r"^" + name + r"=.*$", lambda match: name + "=" + value, source, flags=re.M)
            source = re.sub(r"^SetupIconFile=.*\n", "", source, flags=re.M)
            source = re.sub(r"\[Files\].*?\[Code\]", lambda match:
                            '[Files]\nSource: "' + str(payload) + '"; DestDir: "{app}"\n[Code]', source, flags=re.S)
            source = source.replace("Software\\Microsoft\\Windows\\CurrentVersion\\Run", startup_key)
            source += r'''
<event('CurPageChanged')>
procedure DriveReinstall(CurPageID: Integer);
begin
  if ExpandConstant('{param:AUTOTEST|0}') <> '1' then Exit;
  if CurPageID = wpSelectDir then begin
    SaveStringToFile(ExpandConstant('{param:PAGEPROOF}'), WizardDirValue, False);
    WizardForm.DirEdit.Text := ExpandConstant('{param:CHOSENDIR}');
  end;
  // Let a broken installer finish safely so the missing-page assertion fails
  // without leaving an unattended error screen or writing into AddOns.
  if CurPageID = wpReady then
    WizardForm.DirEdit.Text := ExpandConstant('{param:CHOSENDIR}');
end;
'''
            script = base / "fixture.iss"
            script.write_text(source, encoding="utf-8")
            compiled = subprocess.run([compiler(), "/Q", str(script)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            try:
                # Simulate a legacy installation removed by an addon update, with only
                # its Windows registration left. Never touch the real Companion key.
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, uninstall_key, 0,
                                       winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                    for name, value in (("Inno Setup: App Path", str(old)),
                                        ("InstallLocation", str(old)),
                                        ("DisplayName", "MPlusLogs Installer Test"),
                                        ("UninstallString", str(old / "unins000.exe"))):
                        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
                proof = base / "directory-page.txt"
                log = base / "reinstall.log"
                installed = subprocess.run([str(base / "TestSetup.exe"), "/VERYSILENT", "/SP-", "/LANG=english", "/SUPPRESSMSGBOXES", "/NORESTART",
                    "/UPDATECOMPANION=1", "/AUTOTEST=1", "/PAGEPROOF=" + str(proof),
                    "/CHOSENDIR=" + str(chosen), "/LOG=" + str(log)], capture_output=True, timeout=30)
                details = log.read_text(encoding="utf-8-sig", errors="replace")
                self.assertTrue(proof.exists(), "Reinstall skipped directory selection:\n" + details)
                self.assertEqual(proof.read_text(), str(old))
                self.assertEqual(installed.returncode, 0, details)
                self.assertTrue((chosen / "fixture.txt").exists())
                self.assertFalse(old.exists())
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, uninstall_key, 0,
                                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                    self.assertEqual(winreg.QueryValueEx(key, "InstallLocation")[0].rstrip("\\"), str(chosen))
                    self.assertIn(str(chosen), winreg.QueryValueEx(key, "UninstallString")[0])
                self.assertTrue((chosen / "unins000.exe").is_file())
            finally:
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, uninstall_key, winreg.KEY_WOW64_64KEY)

    def test_existing_autostart_can_be_read_during_wizard_initialization(self):
        import winreg
        code = (ROOT / "packaging/companion.iss").read_text(encoding="utf-8").split("[Code]", 1)[1]
        registry = "Software\\MPlusLogsInstallerTest-" + uuid.uuid4().hex
        code = code.replace("Software\\Microsoft\\Windows\\CurrentVersion\\Run", registry)
        with tempfile.TemporaryDirectory(prefix="MPlusLogs-installer-test-") as temporary:
            base = Path(temporary)
            payload = base / "fixture.txt"
            payload.write_text("isolated installer fixture")
            destination = base / "chosen install directory"
            script = base / "fixture.iss"
            script.write_text(f'''[Setup]
AppName=MPlusLogs Installer Regression Test
AppVersion=1.0
AppId=MPlusLogs-Test-{uuid.uuid4().hex}
DefaultDirName={base / "default directory"}
PrivilegesRequired=lowest
Uninstallable=no
CreateUninstallRegKey=no
UsePreviousAppDir=no
UsePreviousTasks=no
DisableDirPage=no
DisableProgramGroupPage=yes
OutputDir={base}
OutputBaseFilename=TestSetup
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[CustomMessages]
StartupPageTitle=Startup
StartupPageDescription=Startup
StartupPageNote=Startup
StartupWindows=Windows
StartupRetail=Retail
StartupManual=Manual
StartupRegistryWarning=Registry error
UnsafeInstallDirectory=Companion cannot be installed inside Interface/AddOns
[Files]
Source: "{payload}"; DestDir: "{{app}}"
[Code]
{code}
<event('CurStepChanged')>
procedure VerifySelection(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(AddBackslash(WizardDirValue) + 'selection.txt', IntToStr(StartupPage.SelectedValueIndex), False);
end;
''', encoding="utf-8")
            compiled = subprocess.run([compiler(), "/Q", str(script)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            try:
                for value, mode, expected in (("MPlusLogs Companion", "--background", "0"),
                                               ("MPlusLogs Retail Launcher", "--watch-retail", "1")):
                    for quoted in (True, False):
                        executable = str(destination / "MPlusLogs-Companion.exe")
                        command = ('"' + executable + '"' if quoted else executable) + ' ' + mode
                        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, registry) as key:
                            for name in ("MPlusLogs Companion", "MPlusLogs Retail Launcher"):
                                try: winreg.DeleteValue(key, name)
                                except FileNotFoundError: pass
                            winreg.SetValueEx(key, value, 0, winreg.REG_SZ, command)
                        log = base / "install.log"
                        installed = subprocess.run([str(base / "TestSetup.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES",
                            "/NORESTART", "/UPDATECOMPANION=1", "/DIR=" + str(destination), "/LOG=" + str(log)],
                            capture_output=True, timeout=30)
                        self.assertEqual(installed.returncode, 0, log.read_text(encoding="utf-8-sig", errors="replace"))
                        self.assertEqual((destination / "selection.txt").read_text(), expected)
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry) as key:
                            self.assertEqual(winreg.QueryValueEx(key, value)[0], command)
                addon_root = base / 'WoW/Interface/AddOns'
                addon_root.mkdir(parents=True)
                alias = base / 'junction'
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(addon_root)],
                               capture_output=True, check=True)
                addon = addon_root / 'OtherAddon'
                addon.mkdir()
                (addon / 'OtherAddon_Mainline.toc').write_text('## Interface: 120100')
                addon_alias = base / 'addon-junction'
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(addon_alias), str(addon)],
                               capture_output=True, check=True)
                for safe in (addon_root, addon_root / 'Companion'):
                    log = base / 'allowed.log'
                    installed = subprocess.run([str(base / 'TestSetup.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                        '/NORESTART', '/UPDATECOMPANION=1', '/DIR=' + str(safe), '/LOG=' + str(log)],
                        capture_output=True, timeout=30)
                    self.assertEqual(installed.returncode, 0, log.read_text(encoding='utf-8-sig', errors='replace'))
                    self.assertTrue((safe / 'fixture.txt').exists())
                for unsafe in (addon_root / 'MPlusLogs/Companion', alias / 'OtherAddon/Companion', addon_alias / 'Companion'):
                    log = base / 'blocked.log'
                    installed = subprocess.run([str(base / 'TestSetup.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                        '/NORESTART', '/DIR=' + str(unsafe), '/LOG=' + str(log)], capture_output=True, timeout=30)
                    self.assertNotEqual(installed.returncode, 0)
                    self.assertFalse((unsafe / 'fixture.txt').exists())
                    self.assertIn('Companion cannot be installed', log.read_text(encoding='utf-8-sig', errors='replace'))
            finally:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, registry)


if __name__ == "__main__":
    unittest.main()
