"""Build a portable local preview without changing release versions or publishing."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import companion_version

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"release-output/local-history-preview"
NAME="MPlusLogs-Companion-Preview"


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".test-work-preview-",dir=ROOT) as folder:
        metadata=Path(folder)/"companion-build.json"
        metadata.write_text(json.dumps({"version":companion_version.version(),"preview":True}),encoding="utf-8")
        command=[sys.executable,"-m","PyInstaller","--noconfirm","--clean","--onedir","--windowed",
                 "--name",NAME,"--paths",str(ROOT/"tools"),"--hidden-import","retail_launcher",
                 "--hidden-import","release_smoke","--icon",str(ROOT/"tools/assets/mpluslogs.ico"),
                 "--distpath",str(OUTPUT),"--workpath",str(ROOT/"build/local-history-preview"),"--specpath",str(ROOT/"build/local-history-preview")]
        for source,destination in [(ROOT/"tools/assets","assets"),(ROOT/"tools/companion_locales","companion_locales"),
                                   (ROOT/"tools/oauth_client.json","."),(metadata,"."),(ROOT/"realm-slugs.json",".")]:
            command += ["--add-data",f"{source};{destination}"]
        command.append(str(ROOT/"tools/companion_gui.pyw"))
        subprocess.run(command,cwd=ROOT,check=True)
    target=OUTPUT/NAME
    shutil.copy2(ROOT/"realm-slugs.json",target/"realm-slugs.json")
    shutil.copy2(ROOT/"LICENSE",target/"LICENSE.txt")
    shutil.copy2(Path(sys.base_prefix)/"LICENSE.txt",target/"Python-LICENSE.txt")
    (target/"README-local-preview.txt").write_text(
        "Unpublished local preview. Automatic updates are disabled.\n"
        "Exit the installed Companion from its tray menu, then run MPlusLogs-Companion-Preview.exe.\n"
        "Local history > Choose a combat log. No WCL sign-in is needed for local history.\n"
        "In WoW: /reload, /mpl history, Refresh history, Ctrl+C, then Ctrl+V.\n"
        "The entire directory must stay together. Local data is stored in %LOCALAPPDATA%/MPlusLogs.\n",
        encoding="utf-8")
    print(target/ f"{NAME}.exe")


if __name__=="__main__": main()
