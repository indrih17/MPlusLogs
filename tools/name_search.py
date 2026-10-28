"""Bounded, correlated group resolution; unresolved realms never enter profile storage."""
import json
import copy
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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

CLASS_SPECS={
    'WARRIOR':{'Arms','Fury','Protection'}, 'PALADIN':{'Holy','Protection','Retribution'},
    'HUNTER':{'BeastMastery','Marksmanship','Survival'}, 'ROGUE':{'Assassination','Outlaw','Subtlety'},
    'PRIEST':{'Discipline','Holy','Shadow'}, 'DEATHKNIGHT':{'Blood','Frost','Unholy'},
    'SHAMAN':{'Elemental','Enhancement','Restoration'}, 'MAGE':{'Arcane','Fire','Frost'},
    'WARLOCK':{'Affliction','Demonology','Destruction'}, 'MONK':{'Brewmaster','Mistweaver','Windwalker'},
    'DRUID':{'Balance','Feral','Guardian','Restoration'}, 'DEMONHUNTER':{'Havoc','Vengeance','Devourer'},
    'EVOKER':{'Devastation','Preservation','Augmentation'},
}


def candidate_evidence(raw,class_name):
    """Observed WCL role scores, never fabricated from the requested group role.

    Damage and healing repeat leaderboard rows. Keep the best score per dungeon
    and role, and do not sum allStars spec totals (their runs can overlap).
    Missing uploads provide no negative evidence about a character's role.
    """
    character=wcl.character_data(raw)
    roles=set(); specs=set(); points={}; levels=[]
    def observe(spec,positive):
        if spec not in CLASS_SPECS.get(class_name,set()) or not positive: return None
        specs.add(spec)
        role='TANK' if spec in wcl.TANKS else 'HEALER' if spec in wcl.HEALERS else 'DAMAGER'
        roles.add(role)
        return role
    for field in ('damage','healing','performance'):
        if character.get(field) is None: continue
        data=wcl.rankings(character[field])
        for row in data['rankings']:
            score=wcl.numeric(row.get('bestAmount'))
            kills=wcl.numeric(row.get('totalKills'))
            role=observe(row.get('bestSpec') or row.get('spec'),(score or 0)>0 or (kills or 0)>0)
            if role:
                level,_=wcl.score_run(row)
                if level: levels.append(level)
            encounter=row.get('encounter')
            encounter_id=encounter.get('id') if isinstance(encounter,dict) else None
            if role and type(encounter_id) is int and score is not None and score>0:
                key=(role,encounter_id)
                points[key]=max(points.get(key,0),score)
        stars=data.get('allStars')
        for star in stars if isinstance(stars,list) else []:
            if isinstance(star,dict): observe(star.get('spec'),(wcl.numeric(star.get('points')) or 0)>0)
        for run in wcl.throughput_rankings(data.get('throughputRankings'),'candidate').values():
            if not isinstance(run,dict): raise ValueError('Invalid candidate throughput row')
            level=wcl.numeric(run.get('best_level'),100,True)
            if level: levels.append(level)
    scores={role:sum(value for (observed,_),value in points.items() if observed==role)
            for role in ('TANK','HEALER','DAMAGER') if any(key[0]==role for key in points)}
    total=math.fsum(scores.values())
    majority_role=next((role for role,score in scores.items() if score>total/2),None)
    return dict(roles=roles,scores=scores,specs=sorted(specs),majority_role=majority_role,
                best_level=max(levels) if levels else None)


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
        if (len(f) not in {8,9,11} or f[0]!='N' or f[1]!=str(index) or f[2] not in {'eu','us','kr','tw','cn'}
            or not text(f[4]) or f[5] not in CLASSES or f[6] not in {'TANK','HEALER','DAMAGER'}
            or (f[3] and not text(f[3])) or f[7] not in {'known','search','leader'}
            or f[7]=='leader' and not f[3]):
            raise ValueError('Invalid group search member')
        minimum=None
        if len(f)>=9 and (len(f)==9 or f[8]):
            if not f[8].isdigit() or not 1<=int(f[8])<=1000: raise ValueError('Invalid search level')
            minimum=int(f[8])
        key_min=key_max=None
        if len(f)==11:
            if not all(value.isdigit() for value in f[9:11]): raise ValueError('Invalid key context')
            key_min,key_max=map(int,f[9:11])
            if not 2<=key_min<=key_max<=100: raise ValueError('Invalid key context')
        result.append(dict(index=index,region=f[2],realm=f[3],name=f[4],class_name=f[5],role=f[6],origin=f[7],
                           min_level=minimum,key_min=key_min,key_max=key_max))
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


class _RawProfiles:
    """Share each raw cache key across members without racing atomic .tmp writes."""
    def __init__(self,client,cache):
        self.client,self.cache=client,Path(cache)
        self.guard=threading.RLock()
        self.locks={}
        if getattr(client,'name_search_raw',None) is None:client.name_search_raw={}
        self.raw_cache=client.name_search_raw

    def __call__(self,args):
        path=builder.cache_path(self.cache,dict(vars(args),_cache_scope=getattr(self.client,'cache_scope','public')))
        with self.guard:lock=self.locks.setdefault(path,threading.Lock())
        with lock:
            key=(args.region,args.server_slug,args.name.casefold())
            with self.guard:old=self.raw_cache.get(key)
            record=builder.read_cache(path)
            disk_raw=record.get('raw') if record else None
            data=disk_raw.get('data') if isinstance(disk_raw,dict) else None
            fresh=(record and 0<=time.time()-record['fetched_at']<wcl.PROFILE_CACHE_TTL_HOURS*3600
                   and isinstance(data,dict) and isinstance(data.get('gameData'),dict)
                   and wcl.cache_satisfies(disk_raw,args))
            if (old and 0<=time.time()-old[2]<wcl.PROFILE_CACHE_TTL_HOURS*3600
                    and wcl.cache_satisfies(old[1],args)
                    and (not fresh or old[2]>=record['fetched_at'])):
                return old[1],old[2]
            if fresh:return disk_raw,record['fetched_at']
            cancel=getattr(self.client,'cancel',None)
            if cancel is not None and cancel.is_set():raise wcl.ProfileError('Profile loading stopped','retry')
            raw=self.client(args)
            stamp=time.time()
            with self.guard:
                if len(self.raw_cache)>=100:self.raw_cache.clear()
                self.raw_cache[key]=(time.monotonic(),raw,stamp)
            # Preserve valid API data even when role/season verification fails.
            builder.atomic_write(path,json.dumps(dict(fetched_at=stamp,raw=raw),ensure_ascii=False))
            return raw,stamp


def _member_rows(member,mapping,raw_profiles,prepared,lookup_error,
                 error_details,error_codes,available_specs,candidate_info,primary_metric,rank_colors):
    rows=[]
    detail=dict(name=member['name'],region=member['region'],expected_class=member['class_name'],
                key_min=member.get('key_min'),key_max=member.get('key_max'),candidates=[])
    failure_identity=None
    try:
        if lookup_error:raise lookup_error
        if member['realm']:
            candidates=[{'realm_slug':realm_resolver.resolve(mapping,member['region'],member['realm'])}]
        else:
            candidates=prepared['candidates']
            detail.update(prepared['detail'])
        slugs={item['realm_slug'] for item in candidates}
        if not slugs: raise ValueError('No matching character found for this name and class')
        if not 1<=len(slugs)<=6: raise ValueError('Too many search matches; specify a realm')
        matches=[]
        for slug in sorted(slugs):
            args=SimpleNamespace(character_id=None,name=member['name'],server_slug=slug,
                realm=slug,region=member['region'],spec=None,role=member['role'],metric='hps' if member['role']=='HEALER' else 'dps',
                zone=55,season='Midnight M+ Season 2',verify_realm=True,class_name=member['class_name'],
                include_secondary=not primary_metric or not member['realm'])
            raw,fetched_at=raw_profiles(args)
            identity=verified(raw,member,slug,mapping,detail['candidates'])
            if identity:
                if len(slugs)==1: failure_identity=identity
                args.realm=identity['realm']
                evidence=candidate_evidence(raw,member['class_name'])
                profile=None
                try:
                    profile=wcl.normalize(raw,args)
                except wcl.NoSeasonLogs:
                    detail.setdefault('no_season_logs',[]).append(identity['realm'])
                # Above +10, only public season logs may identify an unknown
                # realm. Leaderboard scores alone do not keep a candidate.
                # Hidden profiles and API/schema failures raise before here.
                if (not member['realm'] and (member.get('key_min') or 0)>10
                        and profile is None):
                    detail.setdefault('empty_high_key_excluded',[]).append(identity['realm'])
                    continue
                matches.append((identity,profile,fetched_at,evidence))
        if not matches:
            if detail.get('empty_high_key_excluded'):
                raise wcl.NoSeasonLogs('Публичные логи M+ не найдены')
            raise ValueError('No matching character found for this name and class')
        if len(matches)>1 and not member['realm'] and member.get('key_min'):
            # Compare the listing against each character's highest completed
            # key in this season, across roles. Missing levels cannot exclude
            # a rival. Only equal distances proceed to role-point comparison.
            if all(m[3]['best_level'] is not None for m in matches):
                def distance(match):
                    level=match[3]['best_level']
                    return max(member['key_min']-level,level-member['key_max'],0)
                nearest=min(map(distance,matches))
                matches=[m for m in matches if distance(m)==nearest]
                if len(matches)==1: detail['key_resolved']=[member['key_min'],member['key_max']]
        if len(matches)>1 and not member['realm']:
            compatible=[m for m in matches if member['role']==m[3]['majority_role']]
            # A role needs more than half of this character's dungeon points.
            # Alternate-spec ranks do not override that majority; ties and
            # missing points still require the user to choose the realm.
            if len(compatible)==1 and all(m[3]['majority_role'] for m in matches):
                matches=compatible
                detail['role_resolved']=member['role']
        if len(matches)>1:
            for identity,profile,_,evidence in matches:
                extra=()
                if candidate_info:
                    extra=tuple(evidence['scores'].get(role) for role in ('TANK','HEALER','DAMAGER'))
                    extra+=(profile.get('best') if profile else None,profile.get('runs') if profile else None,','.join(evidence['specs']))
                rows.append(wcl.line('C',member['index'],identity['region'],identity['realm'],identity['name'],member['class_name'],*extra))
            return rows,detail
        identity,profile,fetched_at,_=matches[0]
        failure_identity=identity
        if profile is None: raise wcl.NoSeasonLogs('Публичные логи M+ не найдены')
        profile['updated']=datetime.fromtimestamp(fetched_at,timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        profile['realm']=identity['realm']
        rows.append(wcl.line('P',member['index'],identity['region'],identity['realm'],identity['name'],
                             member['class_name'],wcl.export(profile,available_specs=available_specs,rank_colors=rank_colors)))
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
    return rows,detail


def reply(body,mapping,cache,client,progress=None,error_details=False,error_codes=False,available_specs=False,candidate_info=False,refresh=False,primary_metric=False,rank_colors=False):
    members=parse(body)
    if not client: raise ValueError('Sign in to Warcraft Logs in MPlusLogs Companion')
    search=getattr(client,'name_search',None)
    from name_search_api import ApiSearch
    if search is None:
        search=ApiSearch(client,cache); client.name_search=search
    raw_profiles=_RawProfiles(client,cache)
    rows=['MPLN2']
    diagnostic=dict(updated=time.time(),members=[])

    def snapshot(member,error=None):
        if member['realm']:return None,None
        try:
            key=(member['region'],member['name'].casefold())
            if error and key not in getattr(search,'results',{}):raise error
            candidates=search.for_member(member) if hasattr(search,'for_member') else search(member['name'],member['region'])
            detail={}
            if hasattr(search,'diagnostics'):detail['lookup_diagnostics']=search.diagnostics.get(key,[])
            if hasattr(search,'results'):
                detail['minimum_level']=member.get('min_level')
                detail['lookup_candidates']=search.results.get(key,[])
            return copy.deepcopy(dict(candidates=candidates,detail=detail)),None
        except (ValueError,OSError,KeyError,TypeError) as exc:return None,exc

    def resolve(member,prepared,error):
        return _member_rows(member,mapping,raw_profiles,prepared,error,
                            error_details,error_codes,available_specs,candidate_info,primary_metric,rank_colors)

    if isinstance(search,ApiSearch) and len(members)>1 and getattr(client,'profile_workers',1)>1:
        policy=builder._ProfileWaves(min(5,client.profile_workers))
        maximum=policy.desired(len(members))
        results={};jobs={}
        def collect():
            for index,job in list(jobs.items()):
                if index not in results and job.done():results[index]=job.result()
        def notify(member=None):
            collect()
            if progress:progress(dict(stage='search',completed=len(results),total=len(members),
                character=member['name'] if member else '',realm='',spec=''))
        notify()
        with ThreadPoolExecutor(max_workers=maximum) as pool:
            def ready(member,error=None):
                index=member['index']
                if index in jobs or index in results:return
                prepared,failure=snapshot(member,error)
                jobs[index]=pool.submit(resolve,dict(member),prepared,failure)
                notify(member)
            # The first useful known-realm profile is the quota probe. It is
            # already real work, rather than an extra metadata-only request.
            probe=next((m for m in members if m.get('origin')=='leader' and m['realm']),None)
            probe=probe or next((m for m in members if m['realm']),None)
            if probe is not None:
                prepared,error=snapshot(probe)
                results[probe['index']]=resolve(probe,prepared,error)
                notify(probe)
            search_error=None
            try:search.prepare(members,progress=lambda event:notify(),refresh=refresh,on_ready=ready)
            except (ValueError,OSError,KeyError,TypeError) as exc:search_error=exc
            for member in members:ready(member,search_error)
            for job in as_completed(list(jobs.values())):
                job.result();notify()
        for member in members:
            member_rows,detail=results[member['index']]
            rows.extend(member_rows);diagnostic['members'].append(detail)
    else:
        search_error=None
        if hasattr(search,'prepare'):
            try:
                if isinstance(search,ApiSearch):search.prepare(members,progress=progress,refresh=refresh)
                else:search.prepare(members)
            except (ValueError,OSError,KeyError,TypeError) as exc:search_error=exc
        for index,member in enumerate(members):
            if progress:progress(dict(stage='search',completed=index,total=len(members),
                character=member['name'],realm=member['realm'],spec=''))
            prepared,error=snapshot(member,search_error)
            member_rows,detail=resolve(member,prepared,error)
            rows.extend(member_rows);diagnostic['members'].append(detail)
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
