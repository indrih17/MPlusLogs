"""Only process explicit MPlusLogs request envelopes, never arbitrary clipboard text."""
import re
from urllib.parse import quote
import clipboard_companion as bridge


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
    if len(parts)!=3 or parts[0]!="MPLS1" or not re.fullmatch(r"\d+-\d+",parts[1]):
        return None
    if not parts[2].startswith(("MPLQ1\n","MPLQ2\n")):
        return None
    return parts[1],parts[2]


def reply(text,mapping,cache,client=None,diagnostic=False):
    request=unwrap_request(text)
    if not request: return None
    request_id,body=request
    if diagnostic:
        # Validate identity and request format even in a no-network test.
        import realm_resolver
        realm_resolver.parse_queue(body,mapping)
        message="Связь работает: Ctrl+C > помощник > Ctrl+V. Проверка без WCL, логи не запрашивались."
        return "MPLE1\n"+request_id+"\n"+quote(message,safe="")
    try:
        batch=body.startswith("MPLQ2\n")
        result,_=bridge.process_request(body,mapping,cache,client,batch=batch)
        # WoW EditBox expands clipboard tabs to spaces. Encode the entire
        # data block, including delimiters, before handing it to the game.
        return "MPLS1\n"+request_id+"\nMPLB1\n"+quote(result,safe="")
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return "MPLE1\n"+request_id+"\n"+quote(str(exc),safe="")
