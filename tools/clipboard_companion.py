"""Local Windows helper: explicit MPLQ1 clipboard request -> WCL API -> MPL1 clipboard reply."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time
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

    def __call__(self, args):
        now = time.monotonic()
        if now - self.started >= 3600:
            self.queries, self.started = 0, now
        if self.queries >= self.limit:
            raise ValueError("Local hourly query limit reached; use cache or wait")
        if self.remaining is not None and now < self.budget_reset and self.remaining < 100:
            raise ValueError("WCL API budget is low; wait for reset")
        key = builder.cache_path(Path(), dict({"realm": ""}, **vars(args), _cache_scope=self.cache_scope)).stem
        delay = self.budget.reserve(key, pace=True)
        if delay:
            time.sleep(delay)
        self.queries += 1
        try:
            self.token = self.token_provider() if self.token_provider else self.token or wcl.access_token(self.client_id,self.secret)
            result = wcl.fetch(args,self.token,endpoint="user") if self.token_provider else wcl.fetch(args,self.token)
        except ValueError as exc:
            self.budget.failure(exc)
            if getattr(exc, "status", None) == 401 or "WCL HTTP 401" in str(exc):
                self.token = None
            if self.invalidate_token and "WCL HTTP 401" in str(exc):
                self.invalidate_token()
            raise
        limit = result.get("data",{}).get("rateLimitData")
        if limit:
            self.remaining = limit["limitPerHour"] - limit["pointsSpentThisHour"]
            self.budget_reset = now + limit["pointsResetIn"]
        self.budget.observe(limit)
        self.budget.success(key)
        return result


def process_request(text, mapping, cache, fetcher=None, offline=False, ttl_hours=24, batch=False, spec_profiles=False, refresh=False, spec_details=True):
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
    for entry in valid_entries:
        entry['_cache_scope'] = getattr(fetcher, 'cache_scope', 'public')
    profiles, report = builder.build(valid_entries,cache,ttl_hours=ttl_hours,max_fetch=len(entries) if batch else 20,
                                     offline=offline,fetcher=fetcher,refresh=refresh)
    if spec_profiles and not batch and len(valid_entries)==1 and profiles:
        entry=valid_entries[0]
        aggregate=dict(entry,spec=None)
        if entry.get('spec'):
            _, extra=builder.build([aggregate],cache,ttl_hours=ttl_hours,max_fetch=1,offline=offline,fetcher=fetcher,refresh=refresh)
            report['fetched']+=extra['fetched']; report['cacheHits']+=extra['cacheHits']; report['errors']+=extra['errors']
        record=builder.read_cache(builder.cache_path(cache,aggregate))
        raw=record and record.get('raw')
        if raw and not any('429' in e['error'] or 'budget' in e['error'].lower() for e in report['errors']):
            known={p['spec'] for p in profiles}
            entries_for_specs=[dict(entry,spec=spec,role=None) for spec in wcl.logged_specs(raw) if spec not in known]
            # Never relabel combined numbers. Each spec gets a filtered WCL query;
            # normal cache, pacing, quotas and backoff apply to these calls too.
            additional, extra=builder.build(entries_for_specs[:8],cache,ttl_hours=ttl_hours,
                max_fetch=max(0,20-report['fetched']),offline=offline,fetcher=fetcher,refresh=refresh)
            main=next((p.get('primarySpec') for p in profiles if p.get('primarySpec')),None)
            for profile in additional:
                if main: profile['primarySpec']=main
            profiles+=additional
            report['fetched']+=extra['fetched']; report['cacheHits']+=extra['cacheHits']; report['errors']+=extra['errors']
            report['profiles']=len(profiles)
        if not any(profile['spec']!='All specs' for profile in profiles):
            reasons='; '.join(sorted({item['error'] for item in report['errors']}))
            raise ValueError('Could not load specialization profiles. '+(reasons or 'WCL did not provide specialization data.'))
    report['errors'] += [{'character':e['name'],'realm':e['realm'],'error':e['queue_error']} for e in entries if e.get('queue_error')]
    for item in report['errors']:
        message = item['error'].lower()
        if any(term in message for term in ('http 429', 'rate limit', 'hourly query limit', 'api budget is low')):
            budget = getattr(fetcher, 'budget', None)
            reset = budget.snapshot()['resetAt'] if budget else 0
            timer = ('API reset at ' + str(int(reset)) + '; ') if reset else ''
            item['error'] = ('Personal API; ' if getattr(fetcher, 'api_mode', 'shared') == 'personal' else 'Shared API; ') + timer + item['error']
    if not profiles and not batch:
        reasons = sorted({item["error"] for item in report["errors"]})
        raise ValueError("No usable profile: " + "; ".join(reasons))
    # Check duplicate identities and the addon's import size bound before export.
    if profiles: builder.bundle(profiles)
    response = ("MPL2\n" if batch else "MPL1\n") + "".join(wcl.export(p, spec_details=spec_details).removeprefix("MPL1\n") for p in profiles)
    if batch:
        errors={}
        for item in report['errors']:
            errors.setdefault((item['realm'],item['character']),item['error'])
        received={builder.identity(p['region'],p['realm'],p['name']) for p in profiles}
        for entry in entries:
            message=errors.get((entry['realm'],entry['name']))
            if builder.identity(entry['region'],entry['realm'],entry['name']) not in received and not message:
                message="Публичные логи M+ не найдены"
            if message: response+=wcl.line('F',entry['region'],entry['realm'],entry['name'],message[:500])+'\n'
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
