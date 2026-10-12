"""Opt-in repeatability test against the running diagnostic GUI, never WCL.

Sends three fixed local test requests and conditionally restores the original
text. If the user copies different text during the test, it is left untouched.
"""
import json
from pathlib import Path
import time
import tkinter as tk
from urllib.parse import quote
from clipboard_companion import WindowsClipboard

ROOT=Path(__file__).resolve().parents[1]


def run():
    status=json.loads((ROOT / "companion-status.json").read_text(encoding="utf-8"))
    if not status.get("diagnostic") or not status.get("worker_alive") or time.time()-status["updated"]>5:
        raise RuntimeError("A live diagnostic helper is required; no clipboard changes made")
    root=tk.Tk(); root.withdraw(); root.update()
    clipboard=WindowsClipboard(owner=root.winfo_id())
    original=clipboard.read()
    if not original:
        root.destroy()
        raise RuntimeError("Nonempty text clipboard required for safe restore")
    expected=original
    own=set()
    results=[]
    try:
        for index in range(1,4):
            request_id=f"{int(time.time())}-{900+index}"
            request=f"MPLS1\n{request_id}\nMPLQ1\nQ\teu\t{quote('Гордунни')}\t{quote('Киндрих')}\tdps\tGuardian\n"
            if not clipboard.reply_if_unchanged(expected,request):
                raise RuntimeError("Clipboard changed by user; test aborted")
            own.add(request)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                root.update()
                try: current=clipboard.read()
                except OSError:
                    time.sleep(.03); continue
                if current.startswith(f"MPLE1\n{request_id}\n"):
                    own.add(current); expected=current
                    results.append({"round":index,"reply_received":True})
                    break
                if current!=request:
                    raise RuntimeError("Unexpected clipboard change; leaving it untouched")
                time.sleep(.03)
            else:
                expected=request
                results.append({"round":index,"reply_received":False})
                break
        return results
    finally:
        root.update()
        current=clipboard.read()
        if current in own:
            clipboard.reply_if_unchanged(current,original)
        root.destroy()


if __name__=="__main__":
    result=run()
    (ROOT / "experiments/clipboard-repeatability.json").write_text(json.dumps({"diagnostic_only":True,"rounds":result},indent=2),encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit(0 if len(result)==3 and all(r["reply_received"] for r in result) else 1)
