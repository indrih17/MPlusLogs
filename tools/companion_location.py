"""Keep frozen Companion binaries outside WoW's replaceable AddOns directory."""
import json
from itertools import chain
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys

import companion_i18n as i18n
import local_settings

EXECUTABLE = "MPlusLogs-Companion.exe"


def inside_addons(path):
    parts = [part.casefold() for part in PureWindowsPath(str(path)).parts]
    return any(parts[index:index + 2] == ["interface", "addons"] for index in range(len(parts) - 1))


def safe_directory():
    directory = Path(os.environ["LOCALAPPDATA"]) / "Programs/MPlusLogs Companion"
    # Never replace a user's other installation (which could be newer or running).
    for suffix in range(100):
        candidate = directory if suffix == 0 else directory.with_name(f"MPlusLogs Companion {suffix + 1}")
        if not candidate.exists() and not inside_addons(candidate.resolve()):
            return candidate
    raise OSError("No free Companion installation directory")


def copy_runtime(executable, destination):
    """Copy only the frozen payload; never copy or remove addon or user data."""
    executable, destination = Path(executable).resolve(), Path(destination)
    if not inside_addons(executable) or inside_addons(destination.resolve()):
        raise ValueError("Invalid Companion relocation paths")
    source = executable.parent
    runtime = source / "_internal"
    if executable.name.casefold() != EXECUTABLE.casefold() or not runtime.is_dir():
        raise ValueError("Incomplete Companion portable folder")
    json.loads((runtime / "companion-build.json").read_text(encoding="utf-8"))["version"]
    realms = source / "realm-slugs.json"
    if not realms.is_file() or realms.is_symlink():
        raise ValueError("Missing bundled realm data")
    licenses = source / "licenses"
    # A junction inside the payload must not pull unrelated data into the copy.
    trees = [runtime] + ([licenses] if licenses.is_dir() else [])
    for path in chain.from_iterable(chain((tree,), tree.rglob("*")) for tree in trees):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Companion payload contains a filesystem link")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()  # Fail safely if another process claimed this destination.
    try:
        shutil.copy2(executable, destination / EXECUTABLE)
        shutil.copytree(runtime, destination / "_internal")
        shutil.copy2(realms, destination / realms.name)
        if licenses.is_dir():
            shutil.copytree(licenses, destination / licenses.name)
        readme = source / "COMPANION-README.txt"
        if readme.is_file() and not readme.is_symlink():
            shutil.copy2(readme, destination / readme.name)
    except Exception:
        # Only the new, exclusively created destination can be rolled back.
        resolved = destination.resolve()
        if resolved.parent == destination.parent.resolve() and not inside_addons(resolved):
            shutil.rmtree(resolved)
        raise
    return destination / EXECUTABLE


def relocation_script(old_executable, new_executable, parent_pid, arguments, result_root, shortcut_folders=None):
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"
    command_arguments = subprocess.list2cmdline(arguments)
    start = "Start-Process -FilePath $new"
    if command_arguments:
        start += " -ArgumentList " + literal(command_arguments)
    folders = "@([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) 'MPlusLogs Companion'))"
    if shortcut_folders is not None:
        folders = "@(" + ", ".join(literal(folder) for folder in shortcut_folders) + ")"
    return (
        "$ErrorActionPreference = 'Stop'; "
        f"Wait-Process -Id {int(parent_pid)} -ErrorAction SilentlyContinue; "
        f"$old = {literal(old_executable)}; $new = {literal(new_executable)}; "
        "try { "
        # The opt-in Retail watcher also loads this runtime. Stop only this exact
        # executable in this session, never other installations or users' apps.
        "$session = (Get-Process -Id $PID).SessionId; "
        "Get-Process | Where-Object { $_.Id -ne $PID -and $_.SessionId -eq $session -and $_.Path -eq $old } | Stop-Process -Force; "
        r"$key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\Run', $true); "
        "if ($key) { try { foreach ($entry in @(@('MPlusLogs Companion', '--background'), @('MPlusLogs Retail Launcher', '--watch-retail'))) { "
        "$value = $key.GetValue($entry[0]); "
        "if ($value -eq ('\"' + $old + '\" ' + $entry[1]) -or $value -eq ($old + ' ' + $entry[1])) { "
        "$key.SetValue($entry[0], ('\"' + $new + '\" ' + $entry[1])) } } } finally { $key.Close() } }; "
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$folders = {folders}; "
        "foreach ($folder in $folders) { if (Test-Path -LiteralPath $folder) { "
        "Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -File | ForEach-Object { "
        "$shortcut = $shell.CreateShortcut($_.FullName); if ($shortcut.TargetPath -eq $old) { "
        "$shortcut.TargetPath = $new; $shortcut.WorkingDirectory = Split-Path -LiteralPath $new; $shortcut.Save() } } } }; "
        "} catch { "
        f"[IO.File]::WriteAllText({literal(Path(result_root) / 'relocation-error.txt')}, $_.Exception.Message); "
        "Add-Type -AssemblyName System.Windows.Forms; "
        "[System.Windows.Forms.MessageBox]::Show('Companion was copied, but Windows could not update all shortcuts or startup entries. Open the new Companion folder and check Settings.', 'MPlusLogs') | Out-Null "
        "}; "
        + start
    )


def guard():
    """Return True to exit before any watcher, mutex, tray or clipboard starts."""
    if not getattr(sys, "frozen", False):
        return False
    executable = Path(sys.executable).resolve()
    if not inside_addons(executable):
        return False
    import windows_integration
    instance = windows_integration.SingleInstance(namespace="Relocation", notify=False)
    if not instance.primary:
        instance.close()
        return True
    from tkinter import Tk, messagebox
    root = Tk()
    root.withdraw()
    try:
        i18n.set_language(local_settings.load().get("language", "system"))
        destination = safe_directory()
        if not messagebox.askyesno("MPlusLogs Companion", i18n.tr(
                "Companion is inside the WoW AddOns folder and can block addon updates. Move it to {path}? Login and settings will be preserved. Choosing No closes Companion to release the files."
                ).format(path=destination), parent=root):
            return True
        new_executable = copy_runtime(executable, destination)
        result_root = local_settings.PATH.parent
        result_root.mkdir(parents=True, exist_ok=True)
        import companion_update
        companion_update.launch_helper(relocation_script(executable, new_executable, os.getpid(), sys.argv[1:], result_root))
        messagebox.showinfo("MPlusLogs Companion", i18n.tr(
            "Companion will restart from {path}. The old files are kept and will be unlocked after it closes."
        ).format(path=destination), parent=root)
    except (OSError, ValueError, KeyError) as exc:
        messagebox.showerror("MPlusLogs Companion", i18n.tr(
            "Could not relocate Companion: {error}. Companion will close. Install it outside Interface/AddOns and try again."
        ).format(error=exc), parent=root)
    finally:
        root.destroy()
        instance.close()
    return True
