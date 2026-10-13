"""Run the actual installer code with isolated registry values and destinations."""
import os
from pathlib import Path
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
                for unsafe in (addon_root / 'MPlusLogs/Companion', alias / 'Companion'):
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
