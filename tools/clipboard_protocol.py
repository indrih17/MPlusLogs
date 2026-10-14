"""Only process explicit MPlusLogs request envelopes, never arbitrary clipboard text."""
import re
from urllib.parse import quote
import clipboard_companion as bridge
import companion_update

CAPABILITIES = {"dual", "batch", "updater", "specprofiles"}


def describe_clipboard(text):
    """Bounded metadata only; never record unrelated clipboard contents."""
    request=unwrap_request(text)
    if request:
        return {"kind":"request","request_id":request[0],"chars":len(text)}
    if text.startswith(("MPLS1","MPLE1","MPLQ1")):
        return {"kind":"mplus_unrecognized","header":text[:5],"chars":len(text),
                "lf":text.count("\n"),"cr":text.count("\r"),"tabs":text.count("\t")}
    return {"kind":"other"}


def unwrap_request(text):
    text=text.replace("\r\n","\n")
    parts=text.split("\n",2)
    if len(parts)!=3 or parts[0] not in {"MPLS1", "MPLS2"} or not re.fullmatch(r"\d+-\d+",parts[1]):
        return None
    if parts[0] == "MPLS2":
        requirement, separator, body = parts[2].partition("\n")
        if not separator or not re.fullmatch(r"MPLC1 [a-z,]+", requirement):
            return None
        parts[2] = body
    if not parts[2].startswith(("MPLQ1\n","MPLQ2\n")):
        return None
    return parts[1],parts[2]


def reply(text,mapping,cache,client=None,diagnostic=False):
    request=unwrap_request(text)
    if not request: return None
    request_id,body=request
    metadata_requested = text.startswith(("MPLS2\n", "MPLS2\r\n"))
    if metadata_requested:
        required = text.replace("\r\n", "\n").split("\n", 3)[2].split(" ", 1)[1].split(",")
        if not set(required) <= CAPABILITIES:
            return "MPLE1\n" + request_id + "\n" + quote("Для загрузки этих логов обновите MPlusLogs Companion.", safe="")
    if diagnostic:
        # Validate identity and request format even in a no-network test.
        import realm_resolver
        realm_resolver.parse_queue(body,mapping)
        message="Связь работает: Ctrl+C > помощник > Ctrl+V. Проверка без WCL, логи не запрашивались."
        return "MPLE1\n"+request_id+"\n"+quote(message,safe="")
    try:
        batch=body.startswith("MPLQ2\n")
        result,_=bridge.process_request(body,mapping,cache,client,batch=batch,
            spec_profiles=metadata_requested and 'specprofiles' in required)
        # WoW EditBox expands clipboard tabs to spaces. Encode the entire
        # data block, including delimiters, before handing it to the game.
        metadata = "MPLV1 " + companion_update.current_version() + " " + ",".join(sorted(CAPABILITIES)) + "\n" if metadata_requested else ""
        return "MPLS1\n"+request_id+"\n"+metadata+"MPLB1\n"+quote(result,safe="")
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return "MPLE1\n"+request_id+"\n"+quote(str(exc),safe="")
