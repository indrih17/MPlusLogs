"""Build locale files from the addon catalog. Translation is an explicit build step."""
import ast
import concurrent.futures
import json
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FILES = ['Data.lua', 'Transport.lua', 'UI.lua', 'Settings.lua', 'Integration.lua', 'Probe.lua']
TOKEN = re.compile(r'--\[\[.*?\]\]|--[^\n]*|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', re.S)
CYRILLIC = re.compile('[\u0400-\u04ff]')
SKIP = {'Киндрих', 'Гордунни', 'Снимок со скриншота пользователя'}
EXTRA = ['All specs', 'Best %', 'Median %', 'WCL score: ', ' Best / Median: ',
         'Публичные логи M+ не найдены', 'WCL API: M+ по уровню ключа',
         'Снимок со скриншота пользователя']
LOCALES = {'enUS':'en', 'deDE':'de', 'esES':'es', 'esMX':'es', 'frFR':'fr',
           'itIT':'it', 'koKR':'ko', 'ptBR':'pt', 'zhCN':'zh-CN', 'zhTW':'zh-TW'}
CATALOG = ROOT/'Locales'/'catalog.json'

def literals(code):
    for match in TOKEN.finditer(code):
        raw = match.group()
        if raw.startswith('--'): continue
        value = ast.literal_eval(raw)
        if (CYRILLIC.search(value) and len(value)>1 and value not in SKIP) or value in EXTRA[1:5]:
            yield match, value

def extract():
    values = set(EXTRA)
    if CATALOG.exists(): values.update(json.loads(CATALOG.read_text(encoding='utf-8')))
    for name in FILES:
        values.update(value for _,value in literals((ROOT/name).read_text(encoding='utf-8')))
    CATALOG.parent.mkdir(exist_ok=True)
    CATALOG.write_text(json.dumps(sorted(values),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Catalog: {len(values)} strings',flush=True)

def request_translation(values, lang):
    payload=[]; replacements={}
    for index,value in enumerate(values):
        tokens={}
        def protect(match):
            token=f'ZXPH{index}N{len(tokens)}XZ'; tokens[token]=match.group(); return token
        content=re.sub(r'\|c[0-9a-fA-F]{8}|\|r|Ctrl\+[ACV]|/reload|/mpl|MPlusLogs|DPS|HPS|WCL|M\+|%[0-9.*]*[sdif]',protect,value)
        content=content.replace('\n',' ZXNEWLINEXZ ')
        payload.append(content if len(values)==1 else f'ZXSTART{index}XZ {content} ZXEND{index}XZ')
        replacements[index]=tokens
    url='https://translate.googleapis.com/translate_a/single?'+urllib.parse.urlencode(
        {'client':'gtx','sl':'auto','tl':lang,'dt':'t','q':'\n'.join(payload)})
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'MPlusLogs-localization-build/1.0'})
            with urllib.request.urlopen(req,timeout=30) as response: data=json.load(response)
            result=''.join(segment[0] or '' for segment in data[0])
            translated={}
            for index,value in enumerate(values):
                match=re.search(rf'ZXSTART{index}XZ\s*(.*?)\s*ZXEND{index}XZ',result,re.S)
                if len(values)>1 and not match: raise ValueError(f'Missing translation marker {index}')
                text=(result if len(values)==1 else match.group(1)).replace(' ZXNEWLINEXZ ','\n').replace('ZXNEWLINEXZ','\n')
                for token,original in replacements[index].items():
                    if token not in text: raise ValueError(f'Missing protected token {token}')
                    text=text.replace(token,original)
                if not text.strip(): raise ValueError('Empty translation')
                # Preserve whitespace used by existing concatenation sites.
                text=value[:len(value)-len(value.lstrip())]+text.strip()+value[len(value.rstrip()):]
                translated[value]=text
            return translated
        except ValueError:
            if len(values)>1:
                merged={}
                for value in values: merged.update(request_translation([value],lang))
                return merged
            raise
        except Exception:
            if attempt==3: raise
            time.sleep(attempt+1)

def translate():
    values=json.loads(CATALOG.read_text(encoding='utf-8'))
    for locale,lang in LOCALES.items():
        path=CATALOG.parent/(locale+'.json')
        result=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        missing=[value for value in values if value not in result]
        if not missing: continue
        if locale=='esMX' and (CATALOG.parent/'esES.json').exists():
            path.write_text((CATALOG.parent/'esES.json').read_text(encoding='utf-8'),encoding='utf-8'); continue
        chunks=[missing[i:i+5] for i in range(0,len(missing),5)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for translated in pool.map(lambda group: request_translation(group,lang),chunks): result.update(translated)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'{locale}: {len(result)} translated',flush=True)

def lua_string(text):
    return json.dumps(text,ensure_ascii=False)

def repair():
    for locale,lang in LOCALES.items():
        path=CATALOG.parent/(locale+'.json')
        data=json.loads(path.read_text(encoding='utf-8'))
        missing=[key for key,value in data.items() if not value.strip()]
        for key in missing: data.update(request_translation([key],lang))
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if missing: print(f'{locale}: repaired {len(missing)} empty strings',flush=True)

def apply():
    values=json.loads(CATALOG.read_text(encoding='utf-8'))
    for locale in ['enUS','ruRU',*list(LOCALES)[1:]]:
        translations={value:value for value in values} if locale=='ruRU' else json.loads((CATALOG.parent/(locale+'.json')).read_text(encoding='utf-8'))
        if set(translations)!=set(values): raise ValueError(f'Incomplete locale {locale}')
        lines=['-- Generated from Locales/catalog.json; edit translations in the locale JSON.', 'local _, MPL = ...']
        if locale!='enUS': lines.append(f'if MPL.locale ~= {lua_string(locale)} then return end')
        lines.append('local L = MPL.L')
        lines.extend(f'L[{lua_string(value)}] = {lua_string(translations[value])}' for value in values)
        (CATALOG.parent/(locale+'.lua')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name in FILES:
        path=ROOT/name; code=path.read_text(encoding='utf-8')
        for match,value in reversed(list(literals(code))):
            # Already-localized literals are catalog keys, not new expressions.
            if code[max(0,match.start()-2):match.start()]=='L[': continue
            code=code[:match.start()]+'L['+lua_string(value)+']'+code[match.end():]
        if 'local L = MPL.L' not in code: code=code.replace('local _, MPL = ...','local _, MPL = ...\nlocal L = MPL.L',1).replace('local addonName, MPL = ...','local addonName, MPL = ...\nlocal L = MPL.L',1)
        path.write_text(code,encoding='utf-8')
    print('Locale Lua files and addon lookups generated',flush=True)

if __name__=='__main__':
    {'extract':extract,'translate':translate,'repair':repair,'apply':apply}[sys.argv[1]]()
