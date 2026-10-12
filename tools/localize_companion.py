"""Build-time locale catalog and translation drafts; no runtime translation service."""
import ast
import concurrent.futures
import json
from pathlib import Path
import re
import sys
import localize_addon

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path(__file__).with_name("companion_locales")
SOURCES = ("companion_gui.pyw", "wcl_oauth.py", "windows_integration.py", "clipboard_protocol.py")
EXTRA = ["Language", "Follow Windows", "Could not connect to Warcraft Logs",
         "WCL GraphQL error; inspect API schema/query. No export written",
         "Local hourly query limit reached; use cache or wait", "WCL API budget is low; wait for reset",
         "Windows could not protect/read WCL settings for this user", "Invalid MPlusLogs callback.",
         "WCL HTTP {code}. Check your sign-in, API permissions or request limit."]


def write(locale, data):
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY / (locale + ".json")).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def extract():
    values = set(EXTRA)
    for name in SOURCES:
        tree = ast.parse((ROOT / "tools" / name).read_text(encoding="utf-8"))
        values.update(node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)
                      and re.search(r"[А-Яа-яЁё]",node.value))
    write("catalog", sorted(values))
    write("ruRU", {key:key for key in sorted(values)})
    return sorted(values)


def translate(force=False):
    values = json.loads((DIRECTORY / "catalog.json").read_text(encoding="utf-8"))
    targets = localize_addon.LOCALES
    english = json.loads((DIRECTORY / "enUS.json").read_text(encoding="utf-8"))
    for locale,language in targets.items():
        if locale == "enUS" or ((DIRECTORY / (locale+".json")).exists() and not force):
            continue
        if locale == "esMX":
            write(locale,json.loads((DIRECTORY/"esES.json").read_text(encoding="utf-8")))
            continue
        result = {}
        # Single strings avoid truncated sentences around batch translation markers.
        chunks = [[value] for value in values]
        def translate_group(group):
            aliases = {"Warcraft Logs":"DPS", "Retail":"HPS", "Classic":"/reload", "PTR":"/mpl", "{code}":"Ctrl+C"}
            protected = {}
            for key in group:
                text = english[key]
                for original, token in aliases.items():
                    text = text.replace(original,token)
                protected[key] = text
            translated = localize_addon.request_translation(list(protected.values()),language)
            result = {}
            for key,value in protected.items():
                text = translated[value]
                for original, token in aliases.items():
                    if original in english[key]:
                        text = text.replace(token, original)
                result[key] = text
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for group in pool.map(translate_group,chunks):
                result.update(group)
        write(locale,result)
        print(f"{locale}: {len(result)} translations",flush=True)


if __name__ == "__main__":
    {"extract":extract,"translate":lambda:translate("--force" in sys.argv)}[sys.argv[1]]()
