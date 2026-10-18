"""Complete regional identity discovery through the official WCL API only."""
import hashlib
import json
from pathlib import Path
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import build_database as builder
from api_budget import BudgetError


def catalogue():
    path=(Path(__file__).with_name('realm-catalogue-audit.json') if getattr(sys,'frozen',False)
          else Path(__file__).resolve().parents[1]/'packaging/realm-catalogue-audit.json')
    return json.loads(path.read_text(encoding='utf-8'))['regions']


class ApiSearch:
    POSITIVE_TTL=6*3600
    NEGATIVE_TTL=300
    CHECKPOINT_VERSION=1

    def __init__(self,client,cache,servers=None):
        self.client=client
        self.cache=Path(cache)
        self.servers=servers if servers is not None else catalogue()
        self.results={}
        self.stamps={}
        self.errors={}
        self.diagnostics={}

    def _path(self,key):
        scope=getattr(self.client,'cache_scope','public')
        digest=hashlib.sha256(json.dumps([scope,*key,self._catalogue_id(key[0])],ensure_ascii=True).encode()).hexdigest()
        return self.cache/('name-lookup-'+digest+'.json')

    def _catalogue_id(self,region):
        identity=sorted((server['id'],server['slug']) for server in self.servers.get(region,[]))
        return hashlib.sha256(json.dumps(identity).encode()).hexdigest()

    def _checkpoint_path(self,key):
        return self._path(key).with_name(self._path(key).name.replace('name-lookup-','name-scan-'))

    def _load_checkpoint(self,key):
        # A completed alias may represent absence, so partial scans use the
        # short negative TTL even when another realm has a positive candidate.
        record=builder.read_cache(self._checkpoint_path(key))
        if not record or record.get('version')!=self.CHECKPOINT_VERSION:return {}
        entries=record.get('entries')
        if not isinstance(entries,dict):return {}
        realms={s['slug'] for s in self.servers.get(key[0],[])}
        now=time.time();valid={}
        for slug,entry in entries.items():
            if slug not in realms or not isinstance(entry,dict):continue
            stamp=entry.get('fetched_at')
            if (not isinstance(stamp,(int,float)) or isinstance(stamp,bool)
                or not 0<=now-stamp<self.NEGATIVE_TTL):continue
            matches=entry.get('matches')
            if self._valid_cached_matches(key[0],matches) and len(matches)<=1:
                valid[slug]=entry
        return valid

    def _save_checkpoint(self,key,entries):
        builder.atomic_write(self._checkpoint_path(key),json.dumps(dict(
            version=self.CHECKPOINT_VERSION,fetched_at=time.time(),entries=entries),ensure_ascii=False))

    def _valid_cached_matches(self,region,matches):
        realms={server['slug'] for server in self.servers.get(region,[])}
        return isinstance(matches,list) and len(matches)<=len(realms) and all(
            isinstance(c,dict) and isinstance(c.get('realm_slug'),str) and c['realm_slug'] in realms
            and isinstance(c.get('class_name'),str) and c['class_name'].isalpha() and c['class_name'].isupper()
            and isinstance(c.get('level'),int) and not isinstance(c['level'],bool) and c['level']>=0
            for c in matches)

    @staticmethod
    def _ordered_matches(matches):
        return sorted(matches,key=lambda item:(item['realm_slug'],item['class_name'],item['level']))

    def _request_batches(self,tasks,progress):
        batches=[tasks[start:start+80] for start in range(0,len(tasks),80)]
        total=len(batches)
        if not total:return
        completed=0
        def notify():
            if progress:progress(dict(stage='realm_lookup',completed=completed,total=total,character=''))
        notify()
        stop=threading.Event()
        failures=[]
        guard=threading.Lock()
        def request(batch):
            cancel=getattr(self.client,'cancel',None)
            if stop.is_set() or cancel is not None and cancel.is_set():
                raise ValueError('Character search was cancelled')
            fields=[]
            for index,(key,name,server) in enumerate(batch):
                fields.append('c'+str(index)+':character(name:'+json.dumps(name)+
                    ',serverRegion:'+json.dumps(key[0])+',serverSlug:'+json.dumps(server['slug'])+
                    '){id name classID level server{id name slug region{slug}}}')
            query='{rateLimitData{limitPerHour pointsSpentThisHour pointsResetIn currentRequest} gameData{classes{id name}} characterData{'+ ' '.join(fields)+'}}'
            started=time.monotonic()
            try:
                return self.client.query_metadata(query),time.monotonic()-started
            except Exception as exc:
                with guard:
                    if not failures:failures.append(exc)
                    stop.set()
                raise

        maximum=min(50,max(1,getattr(self.client,'profile_workers',1)))
        policy=builder._ProfileWaves(maximum)
        policy.desired(total)
        # Learn the cost of one full lookup batch before admitting a wave.
        started=time.monotonic();cpu=time.process_time()
        raw,duration=request(batches[0])
        completed+=1;notify()
        yield batches[0],raw
        policy.observe(1,time.monotonic()-started,time.process_time()-cpu,[duration])
        next_index=1
        capacity=getattr(self.client,'metadata_parallel_capacity',None)
        with ThreadPoolExecutor(max_workers=maximum) as pool:
            while next_index<total:
                desired=policy.desired(total-next_index)
                allowed=min(desired,capacity(desired)) if capacity else 1
                if allowed<=0:
                    budget=getattr(self.client,'budget',None)
                    if budget:budget.check_upstream()
                    reset=budget.snapshot()['resetAt'] if budget else time.time()+60
                    raise BudgetError('Local API safety reserve reached',reset-time.time())
                indexes=list(range(next_index,min(total,next_index+allowed)))
                next_index+=len(indexes)
                started=time.monotonic();cpu=time.process_time()
                jobs={pool.submit(request,batches[index]):index for index in indexes}
                responses={}
                error=None
                for job in as_completed(jobs):
                    try:
                        response=job.result()
                        responses[jobs[job]]=response
                    except Exception as exc:
                        if error is None:error=exc
                        response=None
                    completed+=1;notify()
                    # Validate on the coordinator immediately: a completed name
                    # can load profiles while another batch is still in flight.
                    if response is not None:yield batches[jobs[job]],response[0]
                if error is not None:raise failures[0] if failures else error
                policy.observe(len(indexes),time.monotonic()-started,time.process_time()-cpu,
                               [responses[index][1] for index in indexes])

    def prepare(self,members,progress=None,refresh=False,on_ready=None):
        notified=set()
        def ready(member):
            identity=('index',member['index']) if 'index' in member else ('object',id(member))
            if identity not in notified:
                notified.add(identity)
                if on_ready:on_ready(member)
        missing={}
        for member in members:
            if member['realm']: continue
            key=(member['region'],member['name'].casefold())
            if refresh:
                self.results.pop(key,None)
                self.stamps.pop(key,None)
                self._path(key).unlink(missing_ok=True)
                self._checkpoint_path(key).unlink(missing_ok=True)
            if key in self.results:
                ttl=self.POSITIVE_TTL if self.results[key] else self.NEGATIVE_TTL
                if 0<=time.time()-self.stamps[key]<ttl:
                    self.results[key]=self._ordered_matches(self.results[key])
                    self.errors.pop(key,None)
                    continue
                del self.results[key]
            record=builder.read_cache(self._path(key))
            if (record and self._valid_cached_matches(member['region'],record.get('matches'))
                and 0<=time.time()-record['fetched_at']<(self.POSITIVE_TTL if record['matches'] else self.NEGATIVE_TTL)):
                self.results[key]=self._ordered_matches(record['matches'])
                self.stamps[key]=record['fetched_at']
                self.errors.pop(key,None)
            else: missing[key]=member['name']
        # Every already usable member is admitted before discovery HTTP starts.
        # Duplicate names still represent separate requested group members.
        for member in members:
            if member['realm'] or (member['region'],member['name'].casefold()) not in missing:
                ready(member)
        # No partial scan is ever exposed as a unique match or negative cache.
        checkpoints={key:self._load_checkpoint(key) for key in missing}
        found={key:[] for key in missing}
        for key,entries in checkpoints.items():
            for entry in entries.values():
                for candidate in entry['matches']:
                    if candidate not in found[key]:found[key].append(candidate)
        errors={}
        for key in missing:
            self.errors[key]='Incomplete character lookup response; retry later'
            self.diagnostics[key]=[]
        server_ids={region:{server['id']:server['slug'] for server in servers}
                    for region,servers in self.servers.items()}
        tasks=[]
        for (region,name_key),name in missing.items():
            servers=self.servers.get(region)
            if not servers: raise ValueError('Character search is unavailable for this region')
            for server in servers:
                if server['slug'] not in checkpoints[(region,name_key)]:
                    tasks.append(((region,name_key),name,server))
        finalized=set()
        def finish_complete():
            for key,matches in found.items():
                if key in finalized or key in errors or len(checkpoints[key])!=len(self.servers[key[0]]):continue
                matches=self._ordered_matches(matches)
                stamp=time.time()
                builder.atomic_write(self._path(key),json.dumps(dict(fetched_at=stamp,matches=matches),ensure_ascii=False))
                self.results[key]=matches
                self.stamps[key]=stamp
                self.errors.pop(key,None)
                self._checkpoint_path(key).unlink(missing_ok=True)
                finalized.add(key)
                for member in members:
                    if not member['realm'] and (member['region'],member['name'].casefold())==key:
                        ready(member)
        finish_complete()
        for batch,raw in self._request_batches(tasks,progress):
            data=raw.get('data') if isinstance(raw,dict) else None
            chars=data.get('characterData') if isinstance(data,dict) else None
            game=data.get('gameData') if isinstance(data,dict) else None
            classes=game.get('classes') if isinstance(game,dict) else None
            if not isinstance(chars,dict) or not isinstance(classes,list):
                raise ValueError('Invalid character lookup response')
            response_errors=raw.get('errors',[])
            if not isinstance(response_errors,list):raise ValueError('Invalid character lookup response')
            failed_aliases=set()
            for error in response_errors:
                path=error.get('path') if isinstance(error,dict) else None
                if not isinstance(path,list) or 'characterData' not in path:
                    raise ValueError('Incomplete character lookup response; retry later')
                offset=path.index('characterData')+1
                if offset>=len(path) or not isinstance(path[offset],str):
                    raise ValueError('Incomplete character lookup response; retry later')
                failed_aliases.add(path[offset])
            class_names={c['id']:c['name'].replace(' ','').replace('-','').upper()
                for c in classes if isinstance(c,dict) and isinstance(c.get('id'),int) and isinstance(c.get('name'),str)}
            if not class_names: raise ValueError('Invalid class lookup response')
            for index,(key,name,server) in enumerate(batch):
                alias='c'+str(index)
                if alias not in chars or alias in failed_aliases:
                    errors[key]='Incomplete character lookup response; retry later'
                    continue
                char=chars[alias]
                if char is None:
                    checkpoints[key][server['slug']]=dict(fetched_at=time.time(),matches=[])
                    continue
                actual=char.get('server') if isinstance(char,dict) else None
                region=actual.get('region') if isinstance(actual,dict) else None
                char=char if isinstance(char,dict) else {}
                actual=actual if isinstance(actual,dict) else {}
                region=region if isinstance(region,dict) else {}
                invalid=[]
                if not isinstance(char.get('name'),str) or not char['name']: invalid.append('name')
                for field in ('id','level'):
                    value=char.get(field)
                    if not isinstance(value,int) or isinstance(value,bool) or value<(1 if field=='id' else 0):
                        invalid.append(field)
                actual_id=actual.get('id')
                canonical=server_ids[key[0]].get(actual_id) if isinstance(actual_id,int) and not isinstance(actual_id,bool) else None
                if canonical is None: invalid.append('server.id')
                if not isinstance(actual.get('slug'),str) or actual.get('slug')!=canonical: invalid.append('server.slug')
                if str(region.get('slug','')).lower()!=key[0]: invalid.append('server.region')
                diagnostic=dict(requested_realm=server['slug'],actual_name=char.get('name'),
                    actual_realm=actual.get('slug'),invalid_fields=invalid)
                if invalid:
                    errors[key]='Invalid character identity in lookup response: '+', '.join(invalid)
                    self.diagnostics[key].append(diagnostic)
                    continue
                # Old name/realm lookups can resolve to renamed or transferred
                # characters. Only the exact current name is a candidate.
                if char['name'].casefold()!=name.casefold():
                    diagnostic['excluded']='renamed character'
                    self.diagnostics[key].append(diagnostic)
                    checkpoints[key][server['slug']]=dict(fetched_at=time.time(),matches=[])
                    continue
                # WCL retains bare historical sightings with no known class
                # or level. They cannot be current M+ characters and do not
                # make a structurally valid regional scan incomplete.
                if char.get('classID')==0 and char['level']==0:
                    checkpoints[key][server['slug']]=dict(fetched_at=time.time(),matches=[])
                    continue
                if char.get('classID') not in class_names:
                    errors[key]='Invalid character class in lookup response: classID'
                    diagnostic['invalid_fields']=['classID']
                    self.diagnostics[key].append(diagnostic)
                    continue
                candidate=dict(realm_slug=canonical,class_name=class_names[char['classID']],level=char['level'])
                checkpoints[key][server['slug']]=dict(fetched_at=time.time(),matches=[candidate])
                if candidate not in found[key]: found[key].append(candidate)
            for key in {task[0] for task in batch}:
                self._save_checkpoint(key,checkpoints[key])
            finish_complete()
        for key,error in errors.items():
            self.errors[key]=error

    def for_member(self,member):
        key=(member['region'],member['name'].casefold())
        if key in self.errors: raise ValueError(self.errors[key])
        return [c for c in self.results[(member['region'],member['name'].casefold())]
                if c['class_name']==member['class_name'] and (not member.get('min_level') or c['level']==member['min_level'])]
