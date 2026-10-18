"""Bounded, correlated group resolution; unresolved realms never enter profile storage."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime,timezone
from types import SimpleNamespace
from urllib.parse import unquote
import realm_resolver
import wcl_sync as wcl
import build_database as builder

CLASSES={'WARRIOR','PALADIN','HUNTER','ROGUE','PRIEST','DEATHKNIGHT','SHAMAN',
         'MAGE','WARLOCK','MONK','DRUID','DEMONHUNTER','EVOKER'}


def text(value):
    return bool(value) and len(value.encode('utf-8'))<=200 and not any(ord(c)<32 or c=='|' for c in value)


def parse(body):
    if len(body.encode('utf-8'))>10000: raise ValueError('Invalid group search request')
    if body.startswith('MPLQ2\nMPLN1\n'): body=body[6:]
    lines=body.splitlines()
    if not lines or lines[0]!='MPLN1' or not 1<=len(lines)-1<=5:
        raise ValueError('Invalid group search request')
    result=[]
    for index,line in enumerate(lines[1:],1):
        f=[unquote(p) for p in line.split('\t')]
        if (len(f) not in {8,9} or f[0]!='N' or f[1]!=str(index) or f[2] not in {'eu','us','kr','tw','cn'}
            or not text(f[4]) or f[5] not in CLASSES or f[6] not in {'TANK','HEALER','DAMAGER'}
            or (f[3] and not text(f[3])) or f[7] not in {'known','search'}):
            raise ValueError('Invalid group search member')
        minimum=None
        if len(f)==9:
            if not f[8].isdigit() or not 1<=int(f[8])<=1000: raise ValueError('Invalid search level')
            minimum=int(f[8])
        result.append(dict(index=index,region=f[2],realm=f[3],name=f[4],class_name=f[5],role=f[6],origin=f[7],min_level=minimum))
    return result


class BrowserSearch:
    def __init__(self,cancel=None,status=None):
        self.cancel=cancel
        self.status=status
        self.cache={}
        self.profile=tempfile.TemporaryDirectory(prefix='MPlusLogs-search-session-')

    def __call__(self,name,region):
        key=(region,name.casefold())
        cached=self.cache.get(key)
        if cached and time.monotonic()-cached[0]<300: return cached[1]
        with tempfile.TemporaryDirectory(prefix='MPlusLogs-search-') as folder:
            source=Path(folder)/'query.json'; target=Path(folder)/'reply.json'
            source.write_text(json.dumps(dict(name=name,region=region,profile_dir=self.profile.name)),encoding='utf-8')
            command=([sys.executable,'--name-search-worker'] if getattr(sys,'frozen',False) else
                     [sys.executable,str(Path(__file__).with_name('name_search_browser.py'))])
            process=subprocess.Popen(command+[str(source),str(target)],stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+160
                notified=False
                while process.poll() is None:
                    if not notified and Path(str(target)+'.verification').exists():
                        notified=True
                        if self.status:
                            self.status('Warcraft Logs is waiting for a browser check. Complete it in the Warcraft Logs window.')
                    if time.monotonic()>deadline or (self.cancel and self.cancel.is_set()):
                        raise ValueError('Search unavailable; retry in MPlusLogs Companion')
                    time.sleep(.2)
                if process.returncode or not target.exists():
                    raise ValueError('Search unavailable; check WebView2 in MPlusLogs Companion')
                data=json.loads(target.read_text(encoding='utf-8'))
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=10)
        self.last_result=data
        if isinstance(data,dict) and data.get('state')=='verification_required':
            raise ValueError('Warcraft Logs browser verification was not completed; retry and complete the check')
        if not isinstance(data,dict) or data.get('state')!='found' or not data.get('candidates'):
            raise ValueError('Search unavailable or incomplete; try again')
        if len(self.cache)>=100: self.cache.clear()
        self.cache[key]=(time.monotonic(),data['candidates'])
        return data['candidates']


def realm_url_key(value):
    # WCL's localized URLs omit accents (including the breve in Russian й).
    value=''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))
    return realm_resolver.normalized(value)


def verified(raw,member,slug,mapping=None,diagnostics=None):
    data=raw.get('data') if isinstance(raw,dict) else None
    if not isinstance(data,dict) or not isinstance(data.get('characterData'),dict):
        raise ValueError('Invalid character verification response')
    char=data['characterData'].get('character')
    if not char:
        if diagnostics is not None: diagnostics.append(dict(slug=slug,rejected=['not_found']))
        return None
    if not isinstance(char,dict) or not isinstance(char.get('name'),str):
        raise ValueError('Invalid character verification response')
    game=data.get('gameData')
    rows=game.get('classes') if isinstance(game,dict) else None
    if not isinstance(rows,list): raise ValueError('Invalid class verification response')
    classes={c['id']:c['name'].replace(' ','').replace('-','').upper()
             for c in rows if isinstance(c,dict) and isinstance(c.get('id'),int) and isinstance(c.get('name'),str)}
    if not classes or 'classID' not in char:
        raise ValueError('Cannot verify character class; update MPlusLogs Companion')
    server=char.get('server') or {}
    if (not isinstance(server,dict) or not isinstance(server.get('name'),str)
        or not isinstance(server.get('slug'),str) or not isinstance(server.get('region'),dict)
        or not isinstance(server['region'].get('slug'),str)):
        raise ValueError('Invalid realm verification response')
    same_realm=(server['slug'].casefold()==slug.casefold()
                or realm_url_key(server['name'])==realm_url_key(slug))
    if not same_realm:
        # WCL search uses localized realm URLs, while the API returns an
        # English canonical slug. Accept only an alias from our realm table.
        try:
            alias=realm_resolver.resolve(mapping if mapping is not None else realm_resolver.load_mappings(),
                                         member['region'],server['name'])
            same_realm=alias.casefold()==slug.casefold()
        except ValueError:
            pass
    if 'worldData' in data:
        world=data['worldData']
        requested=world.get('server') if isinstance(world,dict) else None
        requested_id=requested.get('id') if isinstance(requested,dict) else None
        actual_id=server.get('id')
        if (not isinstance(requested_id,int) or isinstance(requested_id,bool) or requested_id<=0
            or not isinstance(actual_id,int) or isinstance(actual_id,bool) or actual_id<=0):
            raise ValueError('Invalid server ID verification response')
        # The API resolves its own aliases. IDs take precedence over every
        # localized spelling, and a different ID must never pass via a name.
        same_realm=requested_id==actual_id
    rejected=[]
    if char['name'].casefold()!=member['name'].casefold(): rejected.append('name')
    if not same_realm: rejected.append('realm')
    if server['region']['slug'].casefold()!=member['region']: rejected.append('region')
    if classes.get(char['classID'])!=member['class_name']: rejected.append('class')
    # Older raw profile caches predate the level field. Unknown identities
    # already passed the API discovery level check; known realms come from WoW.
    if member.get('min_level') and isinstance(char.get('level'),int) and char['level']!=member['min_level']: rejected.append('level')
    if diagnostics is not None:
        diagnostics.append(dict(slug=slug,actual_name=char['name'],actual_realm=server['name'],
            actual_slug=server['slug'],actual_region=server['region']['slug'],
            actual_class=classes.get(char['classID']),rejected=rejected))
    if rejected: return None
    return dict(name=char['name'],region=member['region'],realm=server['name'],server_slug=server['slug'])


def reply(body,mapping,cache,client,progress=None,error_details=False,error_codes=False):
    members=parse(body)
    if not client: raise ValueError('Sign in to Warcraft Logs in MPlusLogs Companion')
    search=getattr(client,'name_search',None)
    if search is None:
        from name_search_api import ApiSearch
        search=ApiSearch(client,cache); client.name_search=search
    search_error=None
    if hasattr(search,'prepare'):
        try: search.prepare(members)
        except (ValueError,OSError,KeyError,TypeError) as exc: search_error=exc
    rows=['MPLN2']
    diagnostic=dict(updated=time.time(),members=[])
    for index, member in enumerate(members):
        detail=dict(name=member['name'],region=member['region'],expected_class=member['class_name'],candidates=[])
        diagnostic['members'].append(detail)
        if progress:
            progress(dict(stage='search', completed=index, total=len(members),
                          character=member['name'], realm=member['realm'], spec=''))
        failure_identity=None
        try:
            if member['realm']:
                candidates=[{'realm_slug':realm_resolver.resolve(mapping,member['region'],member['realm'])}]
            else:
                # A failed new scan must not discard another name's complete,
                # validated cache entry. Partial scans never enter results.
                if search_error and (member['region'],member['name'].casefold()) not in getattr(search,'results',{}):
                    raise search_error
                if hasattr(search,'diagnostics'):
                    detail['lookup_diagnostics']=search.diagnostics.get((member['region'],member['name'].casefold()),[])
                candidates=search.for_member(member) if hasattr(search,'for_member') else search(member['name'],member['region'])
                if hasattr(search,'results'):
                    detail['minimum_level']=member.get('min_level')
                    detail['lookup_candidates']=search.results.get((member['region'],member['name'].casefold()),[])
            slugs={item['realm_slug'] for item in candidates}
            if not slugs: raise ValueError('No matching character found for this name and class')
            if not 1<=len(slugs)<=6: raise ValueError('Too many search matches; specify a realm')
            matches=[]
            empty_season=False
            for slug in sorted(slugs):
                args=SimpleNamespace(character_id=None,name=member['name'],server_slug=slug,
                    realm=slug,region=member['region'],spec=None,role=member['role'],metric='hps' if member['role']=='HEALER' else 'dps',
                    zone=55,season='Midnight M+ Season 2',verify_realm=True)
                # Existing Client enforces the normal query budget and OAuth.
                raw_cache=getattr(client,'name_search_raw',None)
                if raw_cache is None:
                    raw_cache={}; client.name_search_raw=raw_cache
                key=(member['region'],slug,member['name'].casefold(),member['role'])
                old=raw_cache.get(key)
                disk_path=builder.cache_path(Path(cache),dict(vars(args),
                    _cache_scope=getattr(client,'cache_scope','public')))
                record=builder.read_cache(disk_path)
                disk_raw=record.get('raw') if record else None
                disk_data=disk_raw.get('data') if isinstance(disk_raw,dict) else None
                if old and time.monotonic()-old[0]<3600:
                    raw=old[1]
                    fetched_at=old[2]
                elif (record and 0<=time.time()-record['fetched_at']<3600
                      and isinstance(disk_data,dict)
                      and isinstance(disk_data.get('gameData'),dict)):
                    raw=disk_raw
                    fetched_at=record['fetched_at']
                else:
                    raw=client(args)
                    fetched_at=time.time()
                    if len(raw_cache)>=100: raw_cache.clear()
                    raw_cache[key]=(time.monotonic(),raw,fetched_at)
                    # Persist before verification/normalization: a valid API
                    # response may have been rejected by an older resolver.
                    # Keep it for the same hour as Client's profile cooldown.
                    builder.atomic_write(disk_path,json.dumps(dict(fetched_at=fetched_at,raw=raw),ensure_ascii=False))
                identity=verified(raw,member,slug,mapping,detail['candidates'])
                if identity:
                    if len(slugs)==1: failure_identity=identity
                    args.realm=identity['realm']
                    try:
                        profile=wcl.normalize(raw,args)
                    except wcl.NoSeasonLogs:
                        empty_season=True
                        detail.setdefault('no_season_logs',[]).append(identity['realm'])
                        continue
                    matches.append((identity,profile,fetched_at))
            if not matches:
                if empty_season: raise wcl.NoSeasonLogs('Публичные логи M+ не найдены')
                raise ValueError('No matching character found for this name and class')
            if len(matches)>1:
                for identity,_,_ in matches:
                    rows.append(wcl.line('C',member['index'],identity['region'],identity['realm'],identity['name'],member['class_name']))
                continue
            identity,profile,fetched_at=matches[0]
            profile['updated']=datetime.fromtimestamp(fetched_at,timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            profile['realm']=identity['realm']
            rows.append(wcl.line('P',member['index'],identity['region'],identity['realm'],identity['name'],
                                 member['class_name'],wcl.export(profile)))
        except (ValueError,OSError,KeyError,TypeError) as exc:
            # Lua limits the decoded field in bytes, not Unicode characters.
            message=str(exc).encode('utf-8')[:400].decode('utf-8',errors='ignore')
            if error_codes: message=wcl.wire_error(str(exc),wcl.error_info(exc),limit=400)
            detail['error']=message
            if error_details and failure_identity:
                rows.append(wcl.line('F',member['index'],failure_identity['region'],failure_identity['realm'],
                    failure_identity['name'],member['class_name'],message))
            else:
                rows.append(wcl.line('F',member['index'],message))
    # Latest bounded public identity diagnostics only: no tokens, raw replies,
    # browser contents, or unrelated clipboard data. Logging cannot fail import.
    try:
        builder.atomic_write(Path(cache)/'name-search-diagnostic.json',json.dumps(diagnostic,ensure_ascii=False))
    except OSError:
        pass
    if progress:
        progress(dict(stage='search', completed=len(members), total=len(members), character='', realm='', spec=''))
    result='\n'.join(rows)+'\n'
    if len(result.encode('utf-8'))>500000: raise ValueError('Group search reply is too large')
    return result
