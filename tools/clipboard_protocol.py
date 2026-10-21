"""Only process explicit MPlusLogs request envelopes, never arbitrary clipboard text."""
import re
from urllib.parse import quote
import clipboard_companion as bridge
import companion_update

CAPABILITIES = {"dual", "batch", "updater", "opencompanion", "specprofiles", "refresh", "specdetails", "namesearch", "levelsearch", "keycontext", "nameerrors", "errorcodes", "lazyspecs", "candidateinfo", "rescan", "primarymetric", "leaderfirst", "rankcolors"}


def is_open_updates_command(text):
    return text in {"MPLUI1 OPEN_UPDATES", "MPLUI1 OPEN_UPDATES\n", "MPLUI1 OPEN_UPDATES\r\n"}


def describe_clipboard(text):
    """Bounded metadata only; never record unrelated clipboard contents."""
    if is_open_updates_command(text):
        return {"kind":"open_updates","chars":len(text)}
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
    if not parts[2].startswith(("MPLQ1\n","MPLQ2\n","MPLN1\n")):
        return None
    return parts[1],parts[2]


def reply(text,mapping,cache,client=None,diagnostic=False,progress=None):
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
        if body.startswith(('MPLN1\n','MPLQ2\nMPLN1\n')):
            import name_search
            name_search.parse(body)
        else:
            realm_resolver.parse_queue(body,mapping)
        message="Связь работает: Ctrl+C > помощник > Ctrl+V. Проверка без WCL, логи не запрашивались."
        return "MPLE1\n"+request_id+"\n"+quote(message,safe="")
    try:
        if body.startswith(('MPLN1\n','MPLQ2\nMPLN1\n')):
            if not metadata_requested or 'namesearch' not in required:
                raise ValueError('Group search requires namesearch capability')
            import name_search
            result=name_search.reply(body,mapping,cache,client,progress=progress,error_details='nameerrors' in required,
                                     error_codes='errorcodes' in required, available_specs='lazyspecs' in required,
                                     candidate_info='candidateinfo' in required, refresh='rescan' in required,
                                     primary_metric='primarymetric' in required, rank_colors='rankcolors' in required)
        else:
            batch=body.startswith("MPLQ2\n")
            result,_=bridge.process_request(body,mapping,cache,client,batch=batch,
                spec_profiles=metadata_requested and 'specprofiles' in required,
                refresh=metadata_requested and 'refresh' in required,
                spec_details=metadata_requested and 'specdetails' in required, progress=progress,
                error_codes=metadata_requested and 'errorcodes' in required,
                lazy_specs=metadata_requested and 'lazyspecs' in required,
                primary_metric=metadata_requested and 'primarymetric' in required,
                rank_colors=metadata_requested and 'rankcolors' in required)
        # WoW EditBox expands clipboard tabs to spaces. Encode the entire
        # data block, including tab delimiters, before handing it to the game.
        # Preserve record newlines: one enormous encoded line stalls native
        # EditBox paste/layout. Existing Lua decoders already accept these
        # newlines, and unquoting still restores the exact original payload.
        metadata = "MPLV1 " + companion_update.current_version() + " " + ",".join(sorted(CAPABILITIES)) + "\n" if metadata_requested else ""
        return "MPLS1\n"+request_id+"\n"+metadata+"MPLB1\n"+quote(result,safe="\n")
    except (ValueError,OSError,KeyError,TypeError) as exc:
        message=str(exc)
        if metadata_requested and 'errorcodes' in required:
            message=bridge.wcl.wire_error(message,bridge.wcl.error_info(exc))
        return "MPLE1\n"+request_id+"\n"+quote(message,safe="")
