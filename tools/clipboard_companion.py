"""Local Windows helper: explicit MPLQ1 clipboard request -> WCL API -> MPL1 clipboard reply."""
from __future__ import annotations
import argparse
import json
import math
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
import threading
from api_budget import Budget
import clipboard_history

import build_database as builder
import realm_resolver
import wcl_sync as wcl

ROOT = Path(__file__).resolve().parents[1]


def decode_clipboard_text(data):
    # GlobalSize can include padding after the UTF-16 NUL terminator. Decode
    # only the text, not unused allocation bytes (which can contain garbage).
    end=next((i for i in range(0,len(data)-1,2) if data[i:i+2]==b"\0\0"),None)
    if end is None: raise ValueError("Clipboard text has no terminator")
    return data[:end].decode("utf-16-le")


class WindowsClipboard:
    CF_UNICODETEXT = 13

    def __init__(self, owner=None):
        if sys.platform != "win32":
            raise ValueError("Clipboard mode is supported on Windows; use --request file on other systems")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.OpenClipboard.argtypes = [wintypes.HWND]
        self.user.OpenClipboard.restype = wintypes.BOOL
        self.user.CloseClipboard.restype = wintypes.BOOL
        self.user.EmptyClipboard.restype = wintypes.BOOL
        self.user.GetClipboardData.argtypes = [wintypes.UINT]
        self.user.GetClipboardData.restype = wintypes.HANDLE
        self.user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        self.user.SetClipboardData.restype = wintypes.HANDLE
        self.user.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        self.user.RegisterClipboardFormatW.restype = wintypes.UINT
        self.private_formats = [self.user.RegisterClipboardFormatW(name) for name in (
            "ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")]
        if not all(self.private_formats):
            raise OSError("Could not register private clipboard formats")
        self.user.GetClipboardSequenceNumber.restype = wintypes.DWORD
        self.user.CreateWindowExW.argtypes = [wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,
                                             ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                                             wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,wintypes.LPVOID]
        self.user.CreateWindowExW.restype = wintypes.HWND
        # SetClipboardData requires an owner window. HWND_MESSAGE keeps it hidden.
        # GUI callers provide a window on their main thread, whose event loop
        # handles WM_DESTROYCLIPBOARD even while the worker is doing network I/O.
        self.owner = owner or self.user.CreateWindowExW(0,"STATIC","MPlusLogs clipboard",0,0,0,0,0,wintypes.HWND(-3),None,None,None)
        if not self.owner:
            raise OSError("Could not create clipboard owner")
        self.kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        self.kernel.GlobalAlloc.restype = wintypes.HANDLE
        self.kernel.GlobalLock.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalLock.restype = ctypes.c_void_p
        self.kernel.GlobalUnlock.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalSize.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalSize.restype = ctypes.c_size_t
        self.kernel.GlobalFree.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalFree.restype = wintypes.HANDLE

    def sequence(self):
        return self.user.GetClipboardSequenceNumber()

    def _read_open(self):
        handle = self.user.GetClipboardData(self.CF_UNICODETEXT)
        if not handle:
            return ""
        size = self.kernel.GlobalSize(handle)
        if not size or size > 1000002:
            return ""
        pointer = self.kernel.GlobalLock(handle)
        if not pointer:
            raise OSError("Could not lock clipboard text")
        try:
            return decode_clipboard_text(ctypes.string_at(pointer,size))
        finally:
            self.kernel.GlobalUnlock(handle)

    def read(self):
        if not self.user.OpenClipboard(None):
            raise OSError("Clipboard is busy; retry copying the request")
        try:
            return self._read_open()
        finally:
            self.user.CloseClipboard()

    def _allocate(self, data):
        handle = self.kernel.GlobalAlloc(0x0002, len(data))
        if not handle:
            raise OSError("Clipboard allocation failed")
        pointer = self.kernel.GlobalLock(handle)
        if not pointer:
            self.kernel.GlobalFree(handle)
            raise OSError("Clipboard allocation lock failed")
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            self.kernel.GlobalUnlock(handle)
        return handle

    def write_private(self, response):
        """An explicit user copy may replace the current clipboard, without history."""
        return self._replace(response)

    def reply_if_unchanged(self, expected, response):
        clipboard_history.forget_request(expected)
        return self._replace(response, expected)

    def _replace(self, response, expected=None):
        # Preallocate before clearing anything; Windows owns each transferred handle.
        allocations = {}
        opened = False
        try:
            for format_id in self.private_formats:
                allocations[format_id] = self._allocate(b"\0" * 4)
            allocations[self.CF_UNICODETEXT] = self._allocate((response + "\0").encode("utf-16-le"))
            if not self.user.OpenClipboard(self.owner):
                raise OSError("Clipboard is busy; response saved to file")
            opened = True
            if expected is not None and self._read_open() != expected:
                return False
            if not self.user.EmptyClipboard():
                raise OSError("Clipboard write failed; response saved to file")
            # Publish exclusions before the text, in the same clipboard transaction.
            for format_id, handle in list(allocations.items()):
                if not self.user.SetClipboardData(format_id, handle):
                    raise OSError("Clipboard write failed; response saved to file")
                del allocations[format_id]
            return True
        finally:
            if opened:
                self.user.CloseClipboard()
            for handle in allocations.values():
                self.kernel.GlobalFree(handle)


class Client:
    @property
    def profile_workers(self):
        return 50

    def parallel_capacity(self,remaining_profiles):
        return self._parallel_capacity(remaining_profiles,metadata=False)

    def metadata_parallel_capacity(self,remaining_batches):
        return self._parallel_capacity(remaining_batches,metadata=True)

    def _parallel_capacity(self,remaining,*,metadata):
        with self.lock:
            cost=self.metadata_cost if metadata else self.profile_cost
            snapshot=self.budget.snapshot()
            local_remaining=max(0,self.limit-self.queries)
        if remaining<=0:return 0
        if not local_remaining:return 0
        if snapshot['blockedUntil']>time.time():return 0
        if cost is None or snapshot['resetAt']<=time.time():return 1
        cap=snapshot['limitPerHour']
        spent=snapshot.get('projectedSpentThisHour',snapshot['pointsSpentThisHour'])
        # Match Budget.reserve's conservative unit price, so an admitted wave
        # cannot overfill its own holds after a more expensive profile query.
        cost=max(cost,snapshot.get('requestCostEstimate',cost))
        available=cap-spent-max(100,cap*.1)-snapshot['largestObservedCost']
        # This is an estimate, not a promise that all profiles cost the same.
        # Keep 25% per-query headroom on top of the account quota reserve.
        affordable=max(0,int(available/(cost*1.25)))
        return min(50,remaining,affordable,local_remaining)
    def __init__(self, max_hourly_queries=120, client_id=None, secret=None, token_provider=None, invalidate_token=None,
                 state_path=None, cache_scope="public"):
        self.token = None
        self.queries = 0
        self.started = time.monotonic()
        self.limit = max_hourly_queries
        self.budget_reset = 0
        self.remaining = None
        self.client_id,self.secret=client_id,secret
        self.api_mode = 'personal' if client_id else 'shared'
        self.token_provider=token_provider
        self.invalidate_token=invalidate_token
        self.budget = Budget(state_path, max_hourly_queries)
        self.cache_scope = cache_scope
        self.lock=threading.RLock()
        self.profile_cost=None
        self.metadata_cost=None
        self.request_metrics=[]

    def _record_request(self, result, started, profile, sent, error=None):
        """Bounded cost evidence without identities, query text or credentials."""
        limit=wcl.rate_limit_data(result)
        if not limit: limit=getattr(error,'rate_limit',None)
        current=limit.get('currentRequest') if isinstance(limit,dict) else None
        cost=current.get('total') if isinstance(current,dict) else None
        if type(cost) not in (int,float) or not math.isfinite(cost) or cost<0:cost=None
        data=result.get('data') if isinstance(result,dict) else None
        character=data.get('characterData') if isinstance(data,dict) else None
        character=character.get('character') if isinstance(character,dict) else None
        variants=[key for key in ('damage','healing','performance') if isinstance(character,dict) and character.get(key) is not None]
        try:payload_bytes=len(json.dumps(result,ensure_ascii=False).encode('utf-8')) if result is not None else None
        except (ValueError,TypeError):payload_bytes=None
        sample=dict(kind='profile' if profile else 'realm_lookup',metrics=variants,
                    at=int(time.time()),seconds=round(max(0,time.monotonic()-started),3),
                    points=cost,payloadJsonBytes=payload_bytes,sent=sent,
                    outcome='error' if error else 'success')
        with self.lock:
            self.request_metrics.append(sample)
            del self.request_metrics[:-200]

    def save_request_metrics(self,path):
        with self.lock: samples=list(self.request_metrics)
        try:
            builder.atomic_write(Path(path),json.dumps(dict(version=1,requests=samples,
                counters=self.budget.snapshot()['counters']),ensure_ascii=False,indent=2))
        except OSError:
            pass  # Optional local measurements must never stop profile loading.

    def __call__(self, args):
        key = builder.cache_path(Path(), dict({"realm": ""}, **vars(args), _cache_scope=self.cache_scope)).stem
        # An explicit secondary-metric upgrade is distinct from refreshing the
        # same payload. Both shapes still have their own persistent cooldown.
        key += ':primary' if wcl.primary_only_request(args) else ':dual'
        return self._query(key,lambda token:wcl.fetch(args,token,endpoint='user' if self.token_provider else 'client'))

    def query_metadata(self,query):
        import hashlib,json
        key='metadata:'+hashlib.sha256((self.cache_scope+query).encode()).hexdigest()
        def fetch(token):
            endpoint='user' if self.token_provider else 'client'
            result=wcl.request_json(wcl.ROOT+'/api/v2/'+endpoint,json.dumps({'query':query}).encode(),
                {'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            if not isinstance(result,dict) or result.get('errors'):
                raise wcl.APIError('WCL character lookup failed; retry later',
                    rate_limit=wcl.rate_limit_data(result))
            return result
        return self._query(key,fetch,profile=False)

    def _query(self,key,fetch,profile=True):
        started=time.monotonic()
        with self.lock:
            now = time.monotonic()
            if now - self.started >= 3600:
                self.queries, self.started = 0, now
            if self.queries >= self.limit:
                raise ValueError("Local hourly query limit reached; use cache or wait")
            if self.remaining is not None and now < self.budget_reset and self.remaining < 100:
                raise ValueError("WCL API budget is low; wait for reset")
            delay=self.budget.reserve(key,pace=False,profile=profile)
            self.queries += 1
        sent=False
        try:
            cancel=getattr(self,'cancel',None)
            if delay:
                if cancel is not None:
                    if cancel.wait(delay):raise wcl.ProfileError('Profile loading stopped','retry')
                else:time.sleep(delay)
            if cancel is not None and cancel.is_set():raise wcl.ProfileError('Profile loading stopped','retry')
            self.budget.check_upstream(delay)
            with self.lock:
                self.token = self.token_provider() if self.token_provider else self.token or wcl.access_token(self.client_id,self.secret)
                token=self.token
            self.budget.check_upstream(delay)
            sent=True
            result = fetch(token)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self._record_request(None,started,profile,sent,exc)
            error_limit=getattr(exc,'rate_limit',None)
            self.budget.complete(delay,error_limit,sent=sent,
                                 uncertain=sent and self.budget._request_cost(error_limit) is None)
            self.budget.failure(exc)
            if getattr(exc, "status", None) == 401 or "WCL HTTP 401" in str(exc):
                with self.lock:self.token = None
            if self.invalidate_token and "WCL HTTP 401" in str(exc):
                self.invalidate_token()
            raise
        limit = wcl.rate_limit_data(result)
        self._record_request(result,started,profile,sent)
        self.budget.complete(delay,limit)
        if limit:
            with self.lock:
                cost=result.get('data',{}).get('rateLimitData',{}).get('currentRequest',{})
                cost=cost.get('total') if isinstance(cost,dict) else None
                if not profile and type(cost) in (int,float) and cost>0 and math.isfinite(cost):
                    # A short final lookup batch must not lower the estimate
                    # learned from a full batch of realm aliases.
                    self.metadata_cost=max(self.metadata_cost or 0,cost)
                characters=result.get('data',{}).get('characterData')
                character=characters.get('character') if isinstance(characters,dict) else None
                ranked=False
                if isinstance(character,dict) and not character.get('hidden'):
                    for metric in ('damage','healing','performance'):
                        try:ranked=ranked or bool(wcl.rankings(character.get(metric))['rankings'])
                        except (ValueError,KeyError,TypeError):pass
                if profile and ranked and type(cost) in (int,float) and 0<cost<1000000:
                    self.profile_cost=max(self.profile_cost or 0,cost)
                snapshot=self.budget.snapshot()
                self.remaining=snapshot['limitPerHour']-snapshot['pointsSpentThisHour']
                self.budget_reset=time.monotonic()+max(0,snapshot['resetAt']-time.time())
        if profile: self.budget.success(key)
        return result


def process_request(text, mapping, cache, fetcher=None, offline=False, ttl_hours=wcl.PROFILE_CACHE_TTL_HOURS, batch=False, spec_profiles=False, refresh=False, spec_details=True, progress=None, error_codes=False, lazy_specs=False, primary_metric=False, rank_colors=False):
    if not text.startswith(("MPLQ1\n","MPLQ1\r\n","MPLQ2\n","MPLQ2\r\n")):
        raise ValueError("Copy a MPlusLogs request in WoW first")
    batch=batch or text.startswith(("MPLQ2\n","MPLQ2\r\n"))
    entries = realm_resolver.parse_queue(text,mapping,allow_unresolved=batch)
    # Interactive queries are deliberately small. Bulk use belongs to build_database.py.
    if len(entries) > (250 if batch else 20):
        raise ValueError("Слишком много персонажей в одном запросе")
    if len({builder.identity(e['region'],e['realm'],e['name']) for e in entries})!=len(entries):
        raise ValueError("Повторяющиеся кандидаты в запросе")
    valid_entries=[e for e in entries if not e.get('queue_error')]
    def stage_progress(stage):
        if not progress:
            return None
        def notify(completed, total, entry):
            if not total:
                return
            progress(dict(stage=stage, completed=completed, total=total,
                          character=(entry or {}).get('name', ''),
                          realm=(entry or {}).get('realm', ''), spec=(entry or {}).get('spec') or ''))
        return notify
    for entry in valid_entries:
        entry['_cache_scope'] = getattr(fetcher, 'cache_scope', 'public')
        entry['include_secondary'] = not primary_metric
    profiles, report = builder.build(valid_entries,cache,ttl_hours=ttl_hours,max_fetch=len(entries) if batch else 20,
                                     offline=offline,fetcher=fetcher,refresh=refresh,progress=stage_progress('profiles'),
                                     max_workers=getattr(fetcher,'profile_workers',1) if batch else 1)
    if spec_profiles and not lazy_specs and not batch and len(valid_entries)==1 and profiles:
        entry=valid_entries[0]
        aggregate=dict(entry,spec=None)
        if entry.get('spec'):
            _, extra=builder.build([aggregate],cache,ttl_hours=ttl_hours,max_fetch=1,offline=offline,fetcher=fetcher,refresh=refresh,progress=stage_progress('overview'))
            report['fetched']+=extra['fetched']; report['cacheHits']+=extra['cacheHits']; report['errors']+=extra['errors']
        record=builder.read_cache(builder.cache_path(cache,aggregate))
        raw=record and record.get('raw')
        if raw and not any('429' in e['error'] or 'budget' in e['error'].lower() for e in report['errors']):
            known={p['spec'] for p in profiles}
            entries_for_specs=[dict(entry,spec=spec,role=None) for spec in wcl.logged_specs(raw) if spec not in known]
            # Never relabel combined numbers. Each spec gets a filtered WCL query;
            # normal cache, pacing, quotas and backoff apply to these calls too.
            additional, extra=builder.build(entries_for_specs[:8],cache,ttl_hours=ttl_hours,
                max_fetch=max(0,20-report['fetched']),offline=offline,fetcher=fetcher,refresh=refresh,progress=stage_progress('specializations'))
            main=next((p.get('primarySpec') for p in profiles if p.get('primarySpec')),None)
            for profile in additional:
                if main: profile['primarySpec']=main
            profiles+=additional
            report['fetched']+=extra['fetched']; report['cacheHits']+=extra['cacheHits']; report['errors']+=extra['errors']
            report['profiles']=len(profiles)
        if not any(profile['spec']!='All specs' for profile in profiles):
            reasons='; '.join(sorted({item['error'] for item in report['errors']}))
            raise ValueError('Could not load specialization profiles. '+(reasons or 'WCL did not provide specialization data.'))
    report['errors'] += [{'character':e['name'],'region':e['region'],'realm':e['realm'],'error':e['queue_error']} for e in entries if e.get('queue_error')]
    for item in report['errors']:
        message = item['error'].lower()
        if any(term in message for term in ('http 429', 'rate limit', 'hourly query limit', 'api budget is low')):
            budget = getattr(fetcher, 'budget', None)
            reset = budget.snapshot()['resetAt'] if budget else 0
            timer = ('API reset at ' + str(int(reset)) + '; ') if reset else ''
            item['error'] = ('Personal API; ' if getattr(fetcher, 'api_mode', 'shared') == 'personal' else 'Shared API; ') + timer + item['error']
    if not profiles and not batch:
        reasons = sorted({item["error"] for item in report["errors"]})
        detail=next(iter(report["errors"]),{})
        raise wcl.ProfileError("No usable profile: " + "; ".join(reasons),detail.get("error_code","unknown"),detail.get("retry_at",0))
    # Check duplicate identities and the addon's import size bound before export.
    if profiles: builder.bundle(profiles)
    response = ("MPL2\n" if batch else "MPL1\n") + "".join(wcl.export(p, spec_details=spec_details, available_specs=lazy_specs, rank_colors=rank_colors).removeprefix("MPL1\n") for p in profiles)
    if batch:
        errors={}
        for item in report['errors']:
            errors.setdefault(builder.identity(item['region'],item['realm'],item['character']),item)
        received={builder.identity(p['region'],p['realm'],p['name']) for p in profiles}
        for entry in entries:
            detail=errors.get(builder.identity(entry['region'],entry['realm'],entry['name']),{})
            message=detail.get('error')
            if builder.identity(entry['region'],entry['realm'],entry['name']) not in received and not message:
                message="Публичные логи M+ не найдены"
            if message:
                if error_codes: message=wcl.wire_error(message,detail)
                # The Lua importer limits decoded UTF-8 bytes, not characters.
                message=message.encode('utf-8')[:500].decode('utf-8',errors='ignore')
                response+=wcl.line('F',entry['region'],entry['realm'],entry['name'],message)+'\n'
    if len(response.encode('utf-8'))>500000: raise ValueError("Ответ превышает 500 КБ")
    return response, report


def deliver(text, clipboard, mapping, args, client):
    response, report = process_request(text,mapping,args.cache,client,args.offline,args.ttl_hours)
    builder.atomic_write(args.output,response)
    if clipboard and clipboard.reply_if_unchanged(text,response):
        print(f"Ready: {report['profiles']} profile(s). In WoW: Paste reply -> Ctrl+V -> Import.",flush=True)
    else:
        print(f"Reply saved: {args.output}. Clipboard changed/unused; copy this file manually.",flush=True)
    if report["errors"]:
        print("Some data is cached or unavailable; see the source/date in the addon.",flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch",action="store_true",help="Process explicit MPLQ1 clipboard requests until Ctrl+C")
    parser.add_argument("--request",type=Path,help="Read one request file instead of clipboard")
    parser.add_argument("--realm-slugs",type=Path,default=ROOT / "realm-slugs.json")
    parser.add_argument("--cache",type=Path,default=ROOT / ".wcl-cache")
    parser.add_argument("--output",type=Path,default=ROOT / "last-result.mpl")
    parser.add_argument("--ttl-hours",type=float,default=24)
    parser.add_argument("--max-hourly-queries",type=int,default=120)
    parser.add_argument("--offline",action="store_true")
    args = parser.parse_args()
    if args.watch and args.request:
        parser.error("Choose --watch or --request")
    if args.ttl_hours < 0 or not 1 <= args.max_hourly_queries <= 1000:
        parser.error("Invalid TTL or hourly limit")
    try:
        mapping = realm_resolver.load_mappings(args.realm_slugs)
        client = Client(args.max_hourly_queries, state_path=args.cache / "api-state.sqlite3")
        if args.request:
            deliver(args.request.read_text(encoding="utf-8-sig"),None,mapping,args,client)
            return 0
        clipboard = WindowsClipboard()
        if not args.watch:
            deliver(clipboard.read(),clipboard,mapping,args,client)
            return 0
        print("MPlusLogs helper ready. Copy a MPLQ1 request from WoW. Ctrl+C here stops the helper.",flush=True)
        print("Unrelated clipboard contents are ignored and are not sent to WCL.",flush=True)
        last_sequence = None
        while True:
            sequence = clipboard.sequence()
            if sequence != last_sequence:
                try:
                    text = clipboard.read()
                    last_sequence = sequence
                    if text.startswith("MPLQ1\n") or text.startswith("MPLQ1\r\n"):
                        print("WCL request received...",flush=True)
                        deliver(text,clipboard,mapping,args,client)
                except (ValueError,OSError,KeyError,TypeError) as exc:
                    print(f"Error: {exc}. Recopy the request to retry.",flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Helper stopped.")
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f"Error: {exc}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
