"""Complete regional identity discovery through the official WCL API only."""
import hashlib
import json
from pathlib import Path
import sys
import time
import build_database as builder


def catalogue():
    path=(Path(__file__).with_name('realm-catalogue-audit.json') if getattr(sys,'frozen',False)
          else Path(__file__).resolve().parents[1]/'packaging/realm-catalogue-audit.json')
    return json.loads(path.read_text(encoding='utf-8'))['regions']


class ApiSearch:
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
        digest=hashlib.sha256(json.dumps([scope,*key],ensure_ascii=True).encode()).hexdigest()
        return self.cache/('name-lookup-'+digest+'.json')

    def _valid_cached_matches(self,region,matches):
        realms={server['slug'] for server in self.servers.get(region,[])}
        return isinstance(matches,list) and len(matches)<=len(realms) and all(
            isinstance(c,dict) and isinstance(c.get('realm_slug'),str) and c['realm_slug'] in realms
            and isinstance(c.get('class_name'),str) and c['class_name'].isalpha() and c['class_name'].isupper()
            and isinstance(c.get('level'),int) and not isinstance(c['level'],bool) and c['level']>=0
            for c in matches)

    def prepare(self,members):
        missing={}
        for member in members:
            if member['realm']: continue
            key=(member['region'],member['name'].casefold())
            if key in self.results:
                ttl=3600 if self.results[key] else 300
                if 0<=time.time()-self.stamps[key]<ttl: continue
                del self.results[key]
            record=builder.read_cache(self._path(key))
            if (record and self._valid_cached_matches(member['region'],record.get('matches'))
                and 0<=time.time()-record['fetched_at']<(3600 if record['matches'] else 300)):
                self.results[key]=record['matches']
                self.stamps[key]=record['fetched_at']
                self.errors.pop(key,None)
            else: missing[key]=member['name']
        # No partial scan is ever exposed as a unique match or negative cache.
        found={key:[] for key in missing}
        errors={}
        for key in missing:
            self.errors.pop(key,None)
            self.diagnostics[key]=[]
        server_ids={region:{server['id']:server['slug'] for server in servers}
                    for region,servers in self.servers.items()}
        tasks=[]
        for (region,name_key),name in missing.items():
            servers=self.servers.get(region)
            if not servers: raise ValueError('Character search is unavailable for this region')
            for server in servers:
                tasks.append(((region,name_key),name,server))
        for start in range(0,len(tasks),80):
            cancel=getattr(self.client,'cancel',None)
            if cancel is not None and cancel.is_set(): raise ValueError('Character search was cancelled')
            batch=tasks[start:start+80]
            fields=[]
            for index,(key,name,server) in enumerate(batch):
                fields.append('c'+str(index)+':character(name:'+json.dumps(name)+
                    ',serverRegion:'+json.dumps(key[0])+',serverSlug:'+json.dumps(server['slug'])+
                    '){id name classID level server{id name slug region{slug}}}')
            query='{rateLimitData{limitPerHour pointsSpentThisHour pointsResetIn} gameData{classes{id name}} characterData{'+ ' '.join(fields)+'}}'
            raw=self.client.query_metadata(query)
            data=raw.get('data') if isinstance(raw,dict) else None
            chars=data.get('characterData') if isinstance(data,dict) else None
            game=data.get('gameData') if isinstance(data,dict) else None
            classes=game.get('classes') if isinstance(game,dict) else None
            if not isinstance(chars,dict) or not isinstance(classes,list):
                raise ValueError('Invalid character lookup response')
            class_names={c['id']:c['name'].replace(' ','').replace('-','').upper()
                for c in classes if isinstance(c,dict) and isinstance(c.get('id'),int) and isinstance(c.get('name'),str)}
            if not class_names: raise ValueError('Invalid class lookup response')
            for index,(key,name,server) in enumerate(batch):
                alias='c'+str(index)
                if alias not in chars:
                    errors[key]='Incomplete character lookup response; retry later'
                    continue
                char=chars[alias]
                if char is None: continue
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
                    continue
                # WCL retains bare historical sightings with no known class
                # or level. They cannot be current M+ characters and do not
                # make a structurally valid regional scan incomplete.
                if char.get('classID')==0 and char['level']==0: continue
                if char.get('classID') not in class_names:
                    errors[key]='Invalid character class in lookup response: classID'
                    diagnostic['invalid_fields']=['classID']
                    self.diagnostics[key].append(diagnostic)
                    continue
                candidate=dict(realm_slug=canonical,class_name=class_names[char['classID']],level=char['level'])
                if candidate not in found[key]: found[key].append(candidate)
        stamp=time.time()
        for key,matches in found.items():
            if key in errors:
                self.errors[key]=errors[key]
                continue
            builder.atomic_write(self._path(key),json.dumps(dict(fetched_at=stamp,matches=matches),ensure_ascii=False))
            self.results[key]=matches
            self.stamps[key]=stamp

    def for_member(self,member):
        key=(member['region'],member['name'].casefold())
        if key in self.errors: raise ValueError(self.errors[key])
        return [c for c in self.results[(member['region'],member['name'].casefold())]
                if c['class_name']==member['class_name'] and (not member.get('min_level') or c['level']==member['min_level'])]
