"""Private WebView2 worker. Exchanges public search results only, never credentials."""
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import quote, unquote, urlsplit

READ_RESULTS = '''(() => {
 const blocked=/just a moment|security verification|human verification|attention required/i.test(document.title)
   || !!document.querySelector('#challenge-stage,iframe[src*="challenges.cloudflare.com"]');
 if(location.origin!=="https://www.warcraftlogs.com") return {state:"unavailable",urls:[]};
 const urls=[...new Set([...document.querySelectorAll('a[href]')]
   .filter(a=>a.getClientRects().length>0).map(a=>a.href)
   .filter(h=>{const u=new URL(h),p=u.pathname.split('/').filter(Boolean);
     return u.origin===location.origin && p.length===4 && p[0]==="character"
       && ["eu","us","kr","tw","cn"].includes(p[1]);}))];
 return {state:blocked?"verification":"ready",complete:document.readyState==="complete",urls,title:document.title,links:document.querySelectorAll('a[href]').length};
})()'''


def candidate(url, name, region):
    parsed=urlsplit(url)
    parts=[unquote(p) for p in parsed.path.strip('/').split('/')]
    if (parsed.scheme!='https' or parsed.hostname!='www.warcraftlogs.com'
        or len(parts)!=4 or parts[0]!='character' or parts[1]!=region
        or parts[3].casefold()!=name.casefold()):
        return None
    return {'name':name,'region':region,'realm_slug':parts[2]}


class SearchSnapshot:
    """Wait for a loaded, stable result list instead of its first link."""
    def __init__(self):
        self.previous=None
        self.since=0

    def update(self,page,name,region,now):
        if not page or page.get('state')!='ready' or not page.get('complete'):
            self.previous=None
            return None
        found={}
        for url in page.get('urls',[]):
            item=candidate(url,name,region)
            if item: found[item['realm_slug']]=item
        keys=tuple(sorted(found))
        if keys!=self.previous:
            self.previous=keys; self.since=now
        if keys and now-self.since>=2:
            return list(found.values())
        return None


def main(input_path,output_path):
    import webview
    request=json.loads(Path(input_path).read_text(encoding='utf-8'))
    name,region=request['name'],request['region']
    result={'state':'unavailable','candidates':[]}
    screens=webview.screens
    monitor=max(0,min(len(screens)-1,int(os.environ.get('MPLUSLOGS_SEARCH_MONITOR','1'))-1))
    window=webview.create_window('MPlusLogs Companion — Warcraft Logs',
        'https://www.warcraftlogs.com/search/?term='+quote(name,safe=''),
        width=1000,height=760,screen=screens[monitor],hidden=not request.get('diagnostic_visible',False))

    def collect():
        deadline=time.monotonic()+30
        shown=False
        page=None
        snapshot=SearchSnapshot()
        try:
            while time.monotonic()<deadline:
                page=window.evaluate_js(READ_RESULTS)
                if page and page['state']=='verification':
                    snapshot.update(page,name,region,time.monotonic())
                    if not shown:
                        window.show(); shown=True
                        Path(str(output_path)+'.verification').write_text('1',encoding='ascii')
                        deadline=time.monotonic()+120
                elif page:
                    found=snapshot.update(page,name,region,time.monotonic())
                    if found:
                        result.update(state='found',candidates=found)
                        break
                time.sleep(.5)
        except Exception:
            result['state']='unavailable'
        finally:
            if result['state']!='found' and shown:
                result['state']='verification_required'
            if result['state']!='found' and page:
                result['page_title']=page.get('title')
                result['page_state']=page.get('state')
                result['link_count']=page.get('links',0)
            Path(output_path).write_text(json.dumps(result),encoding='utf-8')
            window.destroy()
    # A dedicated temporary profile is reused only within this Companion
    # session. Never import another browser's profile, cookies or credentials.
    profile=request.get('profile_dir')
    webview.start(collect,gui='edgechromium',private_mode=not bool(profile),
                  storage_path=profile,debug=False)


if __name__=='__main__':
    main(*sys.argv[1:3])
