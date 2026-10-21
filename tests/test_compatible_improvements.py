"""Mixed-version protocol contracts, field recovery and disposable-cache cleanup."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import test_batch
from test_addon import api_fixture
from test_api_efficiency import dual
import clipboard_protocol as protocol
import local_settings
import cache_maintenance
import realm_resolver
import wcl_sync as wcl
import build_database as builder
from api_budget import BudgetError

ROOT=Path(__file__).resolve().parents[1]
LEGACY=ROOT/"tests/compatibility/v1"


class CompatibilityTests(unittest.TestCase):
    setUp=test_batch.BatchTests.setUp

    def old_addon(self):
        for name in ("Data.lua","Transport.lua","UI.lua","SearchGroup.lua"):
            self.lua.execute("return assert(loadstring(...))",(LEGACY/name).read_text(encoding="utf-8"))("MPlusLogs",self.mpl)
        self.mpl.DecodeCompanionError=None

    def old_companion(self):
        spec=importlib.util.spec_from_file_location("legacy_protocol",LEGACY/"clipboard_protocol.py")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fetch(self,args):
        raw=dual()
        raw["data"]["characterData"]["character"]["name"]=args.name
        return raw

    def exchange(self,helper=protocol,name="Киндрих",fetch=None):
        self.mpl.ShowProfile=lambda *args: None
        _,request=self.mpl.SendRequest(name,"Гордунни","dps","Guardian")
        reply=helper.reply(request,realm_resolver.load_mappings(),self.cache,fetch or self.fetch)
        return request,reply,self.mpl.ReceiveReply(reply,True)

    def test_new_addon_old_companion_loads_with_missing_display_metadata(self):
        old=self.old_companion()
        for _ in range(2):
            request,reply,result=self.exchange(old)
            self.assertNotIn("errorcodes",request)
            self.assertNotIn("rankcolors",request)
            self.assertNotIn("MPLERR1",unquote(reply))
            self.assertEqual(result,(1,None))
            profile=self.mpl.GetProfile("Киндрих","Гордунни","Guardian")[0]
            self.assertEqual(profile.displayMetadata,"companion")
            self.assertIn("MPlusLogs Companion",self.mpl.ProfileDisplayWarning(profile))
        def hidden(_): raise wcl.NoProfile("Rankings hidden: denied", "hidden")
        _,_,result=self.exchange(old,name="Alice",fetch=hidden)
        self.assertEqual(result,0)
        self.assertEqual(self.mpl.GetProfileState("Alice","Гордунни","Guardian").reason,"hidden")

    def test_old_addon_new_companion_never_receives_new_error_format(self):
        self.old_addon()
        _,_,result=self.exchange()
        self.assertEqual(result,(1,None))
        def hidden(_): raise wcl.NoProfile("Rankings hidden: denied", "hidden")
        request,reply,result=self.exchange(name="Alice",fetch=hidden)
        self.assertNotIn("errorcodes",request)
        self.assertNotIn("MPLERR1",unquote(reply))
        self.assertEqual(result,0)
        self.assertEqual(self.mpl.GetProfileState("Alice","Гордунни","Guardian").reason,"hidden")

    def test_new_pair_negotiates_codes_after_success_and_ignores_wording(self):
        request,_,result=self.exchange()
        self.assertNotIn("errorcodes",request)
        self.assertEqual(result,(1,None))
        def hidden(_): raise wcl.NoProfile("Completely changed human explanation", "hidden")
        request,reply,result=self.exchange(name="Alice",fetch=hidden)
        self.assertIn("errorcodes",request)
        self.assertIn("MPLERR1 hidden",unquote(reply))
        self.assertEqual(result,0)
        self.assertEqual(self.mpl.GetProfileState("Alice","Гордунни","Guardian").reason,"hidden")

    def test_structured_ui_hints_do_not_depend_on_the_message(self):
        for code,expected in (("auth","Companion"),("hidden","скрыты"),("empty","не найдены"),
                              ("retry","недоступна"),("budget","лимит"),("network","интернет")):
            with self.subTest(code=code):
                text=self.mpl.CompanionError(wcl.wire_error("Unrecognizable message",dict(error_code=code)))
                self.assertIn(expected.lower(),text.lower())
                self.assertNotIn("MPLERR1",text)
        schema=self.mpl.CompanionError(wcl.wire_error("Unrecognizable message",dict(error_code="schema")))
        self.assertIn(self.mpl.L["\nCompanion не распознал формат ответа Warcraft Logs. Обновите MPlusLogs Companion; если ошибка повторится, сообщите об этой ошибке."].strip(),schema)

    def test_batch_codes_survive_real_lua_import(self):
        self.exchange()
        players=self.lua.table_from([self.lua.table_from(dict(name="Alice",realm="Гордунни",role="DAMAGER")),
                                     self.lua.table_from(dict(name="Bob",realm="Гордунни",role="DAMAGER"))])
        _,request=self.mpl.SendBatchRequest(players)
        def fetch(args):
            if args.name=="Bob": raise wcl.NoProfile("New translated explanation", "empty")
            return self.fetch(args)
        reply=protocol.reply(request,realm_resolver.load_mappings(),self.cache,fetch)
        self.assertEqual(self.mpl.ReceiveReply(reply,True),1)
        self.assertEqual(self.mpl.GetProfileState("Bob","Гордунни","").reason,"empty")
        self.assertNotIn("MPLERR1",self.mpl.lastBatchResult.failures[self.mpl.Key("Bob","Гордунни")].error)

    def test_old_batch_import_accepts_new_companion_mixed_results(self):
        self.old_addon()
        players=self.lua.table_from([self.lua.table_from(dict(name="Alice",realm="Гордунни",role="DAMAGER")),
                                     self.lua.table_from(dict(name="Bob",realm="Гордунни",role="DAMAGER"))])
        _,request=self.mpl.SendBatchRequest(players)
        def fetch(args):
            if args.name=="Bob": raise wcl.NoSeasonLogs("Публичные логи M+ не найдены")
            return self.fetch(args)
        reply=protocol.reply(request,realm_resolver.load_mappings(),self.cache,fetch)
        self.assertNotIn("MPLERR1",unquote(reply))
        self.assertEqual(self.mpl.ReceiveReply(reply,True),1)
        self.assertEqual(self.mpl.GetProfileState("Bob","Гордунни","").reason,"empty")

    def test_budget_retry_time_survives_error_envelope(self):
        self.exchange()
        def fail(_): raise BudgetError("Different quota wording",90)
        _,reply,_=self.exchange(name="Alice",fetch=fail)
        text=unquote(reply)
        self.assertIn("MPLERR1 budget",text)
        message=self.mpl.CompanionError(text.split("\n",2)[2])
        self.assertIn("мин.",message)
        self.assertNotIn("MPLERR1",message)

    def test_old_negative_cache_migrates_without_network_or_losing_reason(self):
        self.exchange()
        entry=dict(name="Alice",realm="Гордунни",server_slug="gordunni",region="eu",spec="Guardian")
        import time
        path=builder.cache_path(self.cache,entry)
        path.write_text(json.dumps(dict(fetched_at=time.time(),negative=True,error="Rankings hidden: old cache")),encoding="utf-8")
        _,reply,result=self.exchange(name="Alice",fetch=lambda _:self.fail("must reuse old cache"))
        self.assertIn("MPLERR1 hidden",unquote(reply))
        self.assertEqual(result,0)


class SearchCompatibilityTests(unittest.TestCase):
    def setUp(self):
        from test_name_search import NameSearchTests
        NameSearchTests.setUp(self)

    def response(self,helper=protocol,old_addon=False,fail=False):
        if old_addon:
            for name in ("Data.lua","Transport.lua","UI.lua","SearchGroup.lua"):
                self.lua.execute("return assert(loadstring(...))",(LEGACY/name).read_text(encoding="utf-8"))("MPlusLogs",self.mpl)
            self.mpl.DecodeCompanionError=None
        from test_name_search import Client
        _,request=self.mpl.BeginSearchGroupRequest()
        reply=helper.reply(request,realm_resolver.load_mappings(),self.cache,Client(fail=fail))
        count=self.mpl.ReceiveSearchGroupReply(reply)
        return request,reply,count

    def test_old_group_search_addon_new_companion(self):
        request,reply,count=self.response(old_addon=True)
        self.assertNotIn("errorcodes",request)
        self.assertNotIn("MPLERR1",unquote(reply))
        self.assertEqual(count,2)

    def test_new_group_search_requires_companion_with_candidate_details(self):
        old=CompatibilityTests.old_companion(self)
        request,reply,result=self.response(helper=old)
        self.assertIn("candidateinfo",request)
        self.assertTrue(reply.startswith("MPLE1\n"))
        self.assertIsNone(result[0])
        self.assertIn("Companion",result[1])

    def test_new_group_search_uses_codes_after_discovery(self):
        self.response()
        # Force the second member's next profile fetch to fail, not hit cache.
        self.mpl.searchGroupWindow.players[2].loaded=None
        client_cache=self.cache
        for path in client_cache.glob("[0-9a-f]"*64+".json"): path.unlink()
        request,reply,count=self.response(fail=True)
        self.assertIn("errorcodes",request)
        self.assertIn("MPLERR1",unquote(reply))
        self.assertEqual(count,1)
        self.assertNotIn("MPLERR1",self.mpl.searchGroupWindow.players[2].error)

    def test_search_preparation_preserves_budget_code_and_retry_time(self):
        self.response()
        from test_name_search import Client
        class BlockedSearch:
            results={}
            def prepare(self,members): raise BudgetError("New quota explanation",90)
        client=Client()
        client.name_search=BlockedSearch()
        self.mpl.searchGroupWindow=None
        self.mpl.ShowSearchGroup(10)
        _,request=self.mpl.BeginSearchGroupRequest()
        reply=protocol.reply(request,realm_resolver.load_mappings(),self.cache,client)
        self.assertIn("MPLERR1 budget",unquote(unquote(reply)))
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),1)
        self.assertNotIn("MPLERR1",self.mpl.searchGroupWindow.players[2].error)


class PublishedCompatibilityTests(unittest.TestCase):
    """Use the real published source, distinct from the later local preview."""
    setUp=test_batch.BatchTests.setUp
    fetch=CompatibilityTests.fetch
    exchange=CompatibilityTests.exchange
    test_new_addon_published_companion=CompatibilityTests.test_new_addon_old_companion_loads_with_missing_display_metadata
    test_published_addon_new_companion=CompatibilityTests.test_old_addon_new_companion_never_receives_new_error_format

    def old_companion(self):
        spec=importlib.util.spec_from_file_location("published_protocol",ROOT/"tests/compatibility/published-v1/clipboard_protocol.py")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def old_addon(self):
        for name in ("Data.lua","Transport.lua","UI.lua"):
            self.lua.execute("return assert(loadstring(...))",(ROOT/"tests/compatibility/published-v1"/name).read_text(encoding="utf-8"))("MPlusLogs",self.mpl)
        self.mpl.DecodeCompanionError=None

    def test_published_batch_new_companion(self):
        self.old_addon()
        players=self.lua.table_from([self.lua.table_from(dict(name="Alice",realm="Гордунни",role="DAMAGER")),
                                     self.lua.table_from(dict(name="Bob",realm="Гордунни",role="DAMAGER"))])
        _,request=self.mpl.SendBatchRequest(players)
        def fetch(args):
            if args.name=="Bob": raise wcl.NoSeasonLogs("Публичные логи M+ не найдены")
            return self.fetch(args)
        reply=protocol.reply(request,realm_resolver.load_mappings(),self.cache,fetch)
        self.assertNotIn("MPLERR1",unquote(reply))
        self.assertEqual(self.mpl.ReceiveReply(reply,True),1)
        failure=self.mpl.lastBatchResult.failures[self.mpl.Key("Bob","Гордунни")]
        self.assertIn("Публичные логи",failure.error)


class PublishedSearchMenuTests(unittest.TestCase):
    def setUp(self):
        from test_name_search import NameSearchTests
        NameSearchTests.setUp(self)

    def test_unknown_or_older_helper_preserves_roster_and_requests_upgrade(self):
        for known in (False,True):
            with self.subTest(known=known):
                if known: self.setUp()
                self.mpl.companionInfo=self.lua.table_from(dict(capabilities=self.lua.table_from({}))) if known else None
                self.lua.execute('buttons={}; Menu.callbacks.MENU_LFG_FRAME_SEARCH_ENTRY(owner,root); buttons[1]()')
                # Session capabilities disappear after reload. Preserve the
                # user's group request and let the published helper negotiate.
                request=self.mpl.downloadWindow.request
                self.assertIn("namesearch",request)
                self.assertIn("MPLQ2\nMPLN1\n",request)
                old=PublishedCompatibilityTests.old_companion(self)
                def fetch(args):
                    self.fail("An unsupported group request must not query WCL")
                response=old.reply(request,realm_resolver.load_mappings(),self.cache,fetch)
                self.assertTrue(response.startswith("MPLE1\n"),response[:120])
                count,error=self.mpl.ReceiveSearchGroupReply(response)
                self.assertIsNone(count)
                self.assertIn("Companion",error)
                self.assertIsNotNone(self.mpl.searchGroupWindow.requestID)
                self.assertEqual(len(self.mpl.searchGroupWindow.requestPlayers),2)


class SettingsRecoveryTests(unittest.TestCase):
    def test_only_invalid_fields_are_reset_and_input_is_unchanged(self):
        original=dict(theme=[],language="future-locale",sound="yes",autostart=True,retail_autostart=False,
                      personal_client_id="valid-id",api_mode="personal",future_option={"keep":True})
        before=copy.deepcopy(original)
        result=local_settings.validate_config(original)
        self.assertEqual(original,before)
        for key in ("theme","language","sound"): self.assertNotIn(key,result)
        for key in ("autostart","retail_autostart","personal_client_id","api_mode","future_option"):
            self.assertEqual(result[key],original[key])

    def test_corrupt_tokens_keep_preferences_and_file_untouched(self):
        with tempfile.TemporaryDirectory(dir=ROOT,prefix=".test-work-") as folder:
            path=Path(folder)/"settings.json"
            for encrypted in ("!invalid-base64!",base64.b64encode(b"invalid-json").decode(),
                              base64.b64encode(b'[]').decode()):
                data=dict(theme="dark",language="ruRU",oauth_dpapi=encrypted)
                path.write_text(json.dumps(data),encoding="utf-8")
                with patch.object(local_settings,"PATH",path),patch.object(local_settings,"crypt",side_effect=lambda data,_:data):
                    result=local_settings.load()
                self.assertEqual(result["theme"],"dark")
                self.assertEqual(result["language"],"ruRU")
                self.assertNotIn("oauth",result)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")),data)

    def test_invalid_expiry_or_quota_cannot_crash_startup(self):
        tokens=dict(access_token="fake-token",expires_at=1000,_account_id=7)
        for expiry in ("later",True,10**400,float("nan"),float("inf")):
            self.assertNotIn("oauth",local_settings.validate_config(dict(theme="dark",oauth=dict(tokens,expires_at=expiry))))
        result=local_settings.validate_config(dict(oauth=dict(tokens,_api_budget={"limit":[]})))
        self.assertEqual(result["oauth"]["access_token"],"fake-token")
        self.assertNotIn("_api_budget",result["oauth"])
        self.assertEqual(tokens["_account_id"],7)


class CacheMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT,prefix=".test-work-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/".wcl-cache"
        self.root.mkdir()
        self.now=2000000000

    def file(self,name,age,content="cached"):
        path=self.root/name
        path.write_text(content,encoding="utf-8")
        os.utime(path,(self.now-age,self.now-age))
        return path

    def test_only_old_owned_files_are_removed(self):
        old=self.file("a"*64+".json",31*86400)
        recent=self.file("b"*64+".json",3600)
        lookup=self.file("name-lookup-"+"c"*64+".json",31*86400)
        protected=[self.file(name,40*86400) for name in ("settings.json","api-state.sqlite3","update-result.json","name-search-diagnostic.json")]
        nested=self.root/"backup"; nested.mkdir()
        (nested/"old.json").write_text("preserve")
        self.assertEqual(cache_maintenance.clean(self.root,now=self.now)["removed"],2)
        self.assertFalse(old.exists()); self.assertFalse(lookup.exists()); self.assertTrue(recent.exists())
        self.assertTrue(all(path.exists() for path in protected))
        self.assertTrue((nested/"old.json").exists())

    def test_size_pressure_removes_oldest_but_preserves_recent_profiles(self):
        oldest=self.file("a"*64+".json",3*86400,"12345")
        older=self.file("b"*64+".json",2*86400,"12345")
        recent=self.file("c"*64+".json",3600,"12345")
        cache_maintenance.clean(self.root,now=self.now,max_bytes=10)
        self.assertFalse(oldest.exists()); self.assertTrue(older.exists()); self.assertTrue(recent.exists())

    def test_stale_temporary_files_and_cleanup_failures_are_safe(self):
        stale=self.file("a"*64+".json.tmp",2*86400)
        active=self.file("b"*64+".json.tmp",60)
        cache_maintenance.clean(self.root,now=self.now)
        self.assertFalse(stale.exists()); self.assertTrue(active.exists())
        old=self.file("c"*64+".json",31*86400)
        with patch.object(Path,"unlink",side_effect=PermissionError("busy")):
            self.assertEqual(cache_maintenance.clean(self.root,now=self.now)["removed"],0)
        self.assertTrue(old.exists())

    def test_wrong_directory_and_linked_root_are_never_cleaned(self):
        sentinel=self.file("a"*64+".json",31*86400)
        with patch.object(cache_maintenance,"linked",return_value=True):
            self.assertEqual(cache_maintenance.clean(self.root,now=self.now)["removed"],0)
        self.assertTrue(sentinel.exists())
        self.assertEqual(cache_maintenance.clean(self.root.parent,now=self.now)["removed"],0)


if __name__=="__main__": unittest.main()
