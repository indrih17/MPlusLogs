"""Per-user configuration; protect WCL secret with Windows DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import math
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
    if not isinstance(data,dict):
        raise ValueError("Invalid MPlusLogs settings")
    # A broken credential must not discard unrelated preferences. Read only:
    # recovery never rewrites the user's file or stores plaintext credentials.
    for encrypted, plain in (("secret_dpapi", "secret"), ("oauth_dpapi", "oauth")):
        data.pop(plain, None)
        if data.get(encrypted):
            try:
                value=crypt(base64.b64decode(data[encrypted],validate=True),False).decode()
                data[plain]=json.loads(value) if plain=="oauth" else value
            except (ValueError,OSError,TypeError):
                data.pop(encrypted,None)
    return validate_config(data)


def validate_config(config):
    """Keep good preferences and unknown future fields; drop only invalid values."""
    result=dict(config)
    choices={"theme":{"system","light","dark"},"api_mode":{"shared","personal"},
             "language":{"system","enUS","ruRU","deDE","esES","esMX","frFR","itIT","ptBR","koKR","zhCN","zhTW"}}
    for key,allowed in choices.items():
        if key in result and (not isinstance(result[key],str) or result[key] not in allowed):
            result.pop(key)
    for key in ("sound","autostart","retail_autostart"):
        if key in result and type(result[key]) is not bool: result.pop(key)
    for key in ("oauth_client_id","personal_client_id","client_id"):
        value=result.get(key)
        if key in result and (not isinstance(value,str) or len(value)>128 or any(c.isspace() for c in value)):
            result.pop(key)
    tokens=result.get("oauth")
    if tokens is not None:
        expiry=tokens.get("expires_at") if isinstance(tokens,dict) else None
        valid=(isinstance(tokens,dict) and isinstance(tokens.get("access_token"),str)
               and bool(tokens["access_token"]) and isinstance(expiry,(int,float))
               and not isinstance(expiry,bool) and 0<=expiry<=253402300799 and math.isfinite(expiry)
               and (tokens.get("refresh_token") is None or isinstance(tokens["refresh_token"],str)))
        if not valid:
            result.pop("oauth",None); result.pop("oauth_dpapi",None)
        else:
            tokens=result["oauth"]=dict(tokens)
            if "_account_id" in tokens and (type(tokens["_account_id"]) is not int or not 0<tokens["_account_id"]<=2147483647):
                tokens.pop("_account_id")
            quota=tokens.get("_api_budget")
            if quota is not None:
                values=[quota.get(key) for key in ("remaining","limit","reset_at")] if isinstance(quota,dict) else []
                if (len(values)!=3 or any(type(v) not in (int,float) or not 0<=v<=253402300799 or not math.isfinite(v) for v in values)
                        or values[1]<=0 or values[0]>values[1]): tokens.pop("_api_budget",None)
    return result


def save_config(config):
    """Persist preferences and DPAPI-protected OAuth tokens, never plaintext tokens."""
    data={key:config[key] for key in ("oauth_client_id","sound","autostart","retail_autostart","theme","language","personal_client_id","api_mode") if key in config}
    if config.get("oauth"):
        data["oauth_dpapi"]=base64.b64encode(crypt(json.dumps(config["oauth"]).encode(),True)).decode()
    PATH.parent.mkdir(parents=True,exist_ok=True)
    tmp=PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(PATH)
