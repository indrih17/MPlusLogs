"""Only process explicit MPlusLogs request envelopes, never arbitrary clipboard text."""
import re
from urllib.parse import quote, unquote
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


def request_characters(text):
    """Read display identities from a validated request, without resolving realms."""
    request=unwrap_request(text)
    if not request:return []
    body=request[1]
    try:
        if body.startswith(('MPLN1\n','MPLQ2\nMPLN1\n')):
            import name_search
            entries=name_search.parse(body)
        else:
            import realm_resolver
            entries=realm_resolver.parse_queue(body,{},allow_unresolved=True)
        return [dict(name=entry['name'],realm=entry['realm']) for entry in entries]
    except (ValueError,KeyError,TypeError):
        # A malformed request must still reach the normal protocol error path.
        return []


def reply_summary(text):
    """Bounded display counts, without treating envelope delivery as loaded logs.

    This is deliberately not the addon's importer. Unknown/truncated formats
    return None so the UI can say only that a reply is ready, never invent a
    success count from the initiating request.
    """
    if not isinstance(text,str) or len(text)>1501000:return None
    parts=text.replace('\r\n','\n').split('\n',2)
    if len(parts)!=3 or parts[0]!='MPLS1' or not re.fullmatch(r'\d+-\d+',parts[1]):return None
    body=parts[2]
    if body.startswith('MPLV1 '):
        _,separator,body=body.partition('\n')
        if not separator:return None
    try:
        if body.startswith('MPLB1\n'):
            encoded=body[len('MPLB1\n'):]
            if re.search(r'%(?![0-9A-Fa-f]{2})',encoded):return None
            body=unquote(encoded,errors='strict')
        if len(body.encode('utf-8'))>500000:return None
        lines=body.splitlines()
        if not lines or len(lines)>12000:return None
        rows=[]
        for line in lines[1:]:
            if not line:continue
            if re.search(r'%(?![0-9A-Fa-f]{2})',line):return None
            rows.append([unquote(field,errors='strict') for field in line.split('\t')])
        if lines[0] in {'MPL1','MPL2'}:
            parsed=_profile_reply_counts(rows,allow_failures=lines[0]=='MPL2')
            if parsed is None:return None
            profiles,failures,cached=parsed
            return dict(available=len(profiles),failed=len(failures),
                        unavailable=len(failures-profiles),cached=len(cached | (profiles & failures)),choices=0)
        if lines[0]=='MPLN2':
            profiles,failures,cached,choices=set(),set(),set(),set()
            for fields in rows:
                tag=fields[0]
                if len(fields)<3 or not fields[1].isdigit() or not 1<=int(fields[1])<=250:return None
                member=int(fields[1])
                if tag=='P' and len(fields)==7:
                    # Embedded profiles must have their own completed record.
                    nested=fields[6].splitlines()
                    if not nested or nested[0]!='MPL1':return None
                    raw_rows=[line.split('\t') for line in nested[1:] if line]
                    if any(re.search(r'%(?![0-9A-Fa-f]{2})',f) for row in raw_rows for f in row):return None
                    parsed=_profile_reply_counts([[unquote(f,errors='strict') for f in row] for row in raw_rows],False)
                    if parsed is None or parsed[0]!={(fields[2].casefold(),fields[3].casefold(),fields[4].casefold())}:return None
                    profiles.add(member)
                    if parsed[2]:cached.add(member)
                elif tag=='F' and len(fields) in {3,7}:failures.add(member)
                elif tag=='C' and len(fields) in {6,12}:choices.add(member)
                else:return None
            if profiles & choices:return None
            return dict(available=len(profiles),failed=len(failures),unavailable=len(failures-profiles),
                        cached=len(cached | (profiles & failures)),choices=len(choices))
    except (UnicodeError,ValueError):
        return None
    return None


def _profile_reply_counts(rows,allow_failures):
    profiles,failures,cached=set(),set(),set()
    variants=set()
    active=None
    for fields in rows:
        tag=fields[0]
        if tag=='P' and active is None and len(fields) in {16,17,19,20} and all(fields[1:4]):
            active=tuple(value.casefold() for value in fields[1:4])
            variant=active+(fields[6],fields[7],fields[16] if len(fields) in {19,20} else '')
            if variant in variants:return None
            variants.add(variant)
            active_cached=fields[13].startswith('WCL API: cached')
        elif tag=='E' and len(fields)==1 and active is not None:
            profiles.add(active)
            if active_cached:cached.add(active)
            active=None
        elif tag=='F' and allow_failures and active is None and len(fields)==5 and all(fields[1:4]):
            failures.add(tuple(value.casefold() for value in fields[1:4]))
        elif tag in {'D','R','A','M'} and active is not None and len(fields)>1:
            continue
        else:return None
    if active is not None:return None
    return profiles,failures,cached


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
