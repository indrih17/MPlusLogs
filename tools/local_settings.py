"""Per-user configuration; protect WCL secret with Windows DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

PATH=Path(os.environ.get("LOCALAPPDATA",str(Path.home()))) / "MPlusLogs/settings.json"


class Blob(ctypes.Structure):
    _fields_=[("size",wintypes.DWORD),("data",ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data,protect):
    library=ctypes.WinDLL("crypt32",use_last_error=True)
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.LocalFree.argtypes=[wintypes.HANDLE]
    buf=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    source=Blob(len(data),buf)
    output=Blob()
    if protect:
        function=library.CryptProtectData
        function.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        ok=function(ctypes.byref(source),"MPlusLogs WCL",None,None,None,1,ctypes.byref(output))
    else:
        function=library.CryptUnprotectData
        function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        ok=function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output))
    if not ok:
        raise ValueError("Windows could not protect/read WCL settings for this user")
    try:
        return ctypes.string_at(output.data,output.size)
    finally:
        kernel.LocalFree(ctypes.cast(output.data,wintypes.HANDLE))


def save(client_id,secret,sound=False):
    PATH.parent.mkdir(parents=True,exist_ok=True)
    data={"client_id":client_id,"secret_dpapi":base64.b64encode(crypt(secret.encode(),True)).decode(),"sound":sound}
    tmp=PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(PATH)


def load():
    if not PATH.exists():
        return {}
    data=json.loads(PATH.read_text(encoding="utf-8"))
    if data.get("secret_dpapi"):
        data["secret"]=crypt(base64.b64decode(data["secret_dpapi"]),False).decode()
    if data.get("oauth_dpapi"):
        data["oauth"]=json.loads(crypt(base64.b64decode(data["oauth_dpapi"]),False).decode())
    return data


def save_config(config):
    """Persist preferences and DPAPI-protected OAuth tokens, never plaintext tokens."""
    data={key:config[key] for key in ("oauth_client_id","sound","autostart","retail_autostart","theme","language","personal_client_id","api_mode","combat_log_path","combat_log_region") if key in config}
    if config.get("oauth"):
        data["oauth_dpapi"]=base64.b64encode(crypt(json.dumps(config["oauth"]).encode(),True)).decode()
    PATH.parent.mkdir(parents=True,exist_ok=True)
    tmp=PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(PATH)
