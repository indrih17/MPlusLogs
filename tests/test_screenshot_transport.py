import io
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "tools"))
sys.path.insert(0,str(ROOT / ".test-deps"))
from lupa.lua51 import LuaRuntime
import screenshot_transport as codec
from test_addon import MOCK,api_fixture,sync,load_locales
from types import SimpleNamespace
from urllib.parse import quote


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.request="MPLS1\n12345-1\nMPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\tGuardian\n"

    def test_lossless_roundtrip(self):
        self.assertEqual(codec.decode_image(codec.encode_image(self.request)),self.request)

    def test_jpeg_roundtrip_and_shift(self):
        from PIL import Image
        stream=io.BytesIO()
        codec.encode_image(self.request,origin=(20,31)).save(stream,format="JPEG",quality=90)
        stream.seek(0)
        self.assertEqual(codec.decode_image(Image.open(stream)),self.request)

    def test_checksum_rejects_changed_data(self):
        image=codec.encode_image(self.request)
        from PIL import ImageDraw
        bit=70
        x,y=24+(bit%64)*6,24+(bit//64)*6
        color=image.getpixel((x+3,y+3))[0]
        ImageDraw.Draw(image).rectangle((x,y,x+5,y+5),fill="white" if color<128 else "black")
        gray=image.convert("L")
        self.assertIsNone(codec.decode_at(gray,24,24,6))


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.lua.execute('''
            MPlusLogsDB={profiles={}}
            function GetServerTime() return 12345 end
            cvars={screenshotQuality="3"}
            function GetCVar(k) return cvars[k] end
            function SetCVar(k,v) cvars[k]=v end
            timers={}; C_Timer={After=function(_,fn) timers[#timers+1]=fn end}
            function Screenshot() shots=(shots or 0)+1 end
        ''')
        self.mpl=self.lua.table()
        load_locales(self.lua,self.mpl)
        for file in ("Data.lua","Snapshot.lua","Transport.lua","UI.lua"):
            self.lua.execute("return assert(loadstring(...))",(ROOT / file).read_text(encoding="utf-8"))("MPlusLogs",self.mpl)
        args=SimpleNamespace(realm="Гордунни",region="eu",zone=55,season="test",spec=None,metric="dps",server_slug=None)
        self.body=sync.export(sync.normalize(api_fixture(),args))

    def test_send_never_captures_screen_or_changes_settings(self):
        id,request=self.mpl.SendRequest("Киндрих","Гордунни","dps","Guardian")
        self.assertEqual(id,"12345-1")
        self.assertTrue(request.startswith("MPLS1\n12345-1\nMPLQ1\n"))
        self.assertEqual(len(self.lua.globals().timers),0)
        self.assertIsNone(self.lua.globals().shots)
        self.assertEqual(self.lua.globals().cvars.screenshotQuality,"3")

    def test_stale_reply_cannot_import(self):
        self.mpl.SendRequest("Киндрих","Гордунни","dps","Guardian")
        result,error=self.mpl.ReceiveReply("MPLS1\nold-id\n"+self.body)
        self.assertIsNone(result)
        self.assertIn("другой",error)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)

    def test_paste_automatically_imports_and_opens_profile(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        edit=self.mpl.downloadWindow.edit
        edit.SetText(edit,"MPLS1\n12345-1\n"+self.body)
        edit.scripts.OnTextChanged(edit,True)
        self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
        self.assertEqual(self.mpl.panel.profile.best,62)
        self.assertFalse(self.mpl.downloadWindow.shown)
        self.assertIsNone(self.mpl.pendingReply)

    def test_delayed_change_notification_does_not_replace_outgoing_request(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        window=self.mpl.downloadWindow
        edit=window.edit
        request=edit.GetText(edit)
        self.assertTrue(request.startswith("MPLS1\n12345-1\nMPLQ1\n"))
        # Real client notifications can arrive after SetText's guard is reset.
        for flag in (False,True):
            edit.scripts.OnTextChanged(edit,flag)
            self.assertEqual(edit.GetText(edit),request)
        self.assertEqual(self.mpl.pendingReply.id,"12345-1")

    def test_partial_paste_header_is_not_treated_as_an_error(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        edit=self.mpl.downloadWindow.edit
        for text in ("MPLS1","MPLS1\n12345-1\n","MPLE1\n12345-1\n"):
            edit.SetText(edit,text)
            edit.scripts.OnTextChanged(edit,True)
            self.assertEqual(edit.GetText(edit),text)

    def test_error_reply_does_not_create_zero_profile(self):
        self.mpl.SendRequest("Киндрих","Гордунни","dps","")
        result,error=self.mpl.ReceiveReply("MPLE1\n12345-1\nNo%20public%20logs")
        self.assertIsNone(result)
        self.assertEqual(error,"No public logs")
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)

    def test_companion_errors_show_actionable_guidance(self):
        cases=(
            ("No usable profile: WCL HTTP 401; check credentials", "/reload", "Warcraft Logs"),
            ("WCL HTTP 403; API permissions", "доступ к API", "Companion"),
            ("WCL HTTP 429; rate limit", "лимит запросов", "Подождите"),
            ("No usable profile: Публичные логи M+ не найдены", "имя персонажа", "нулевой результат"),
            ("No usable profile: Unknown secondary throughputRankings shape", "формат ответа", "Обновите MPlusLogs Companion"),
            ("Could not connect to Warcraft Logs", "интернет", "попробуйте снова"),
            ("Clipboard is busy; retry copying the request", "буфер обмена", "Ctrl+C"),
        )
        for message, hint, also in cases:
            with self.subTest(message=message):
                self.mpl.ShowDownload("Киндрих","Гордунни",None)
                window=self.mpl.downloadWindow
                request_id=window.request.split("\n")[1]
                window.edit.SetText(window.edit,"MPLE1\n"+request_id+"\n"+quote(message,safe=""))
                window.edit.scripts.OnTextChanged(window.edit,True)
                self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
                self.assertIn(hint,window.status.text)
                self.assertIn(also,window.status.text)

    def test_quota_timer_uses_reply_reset_and_only_shared_recommends_switching(self):
        for mode,label in (("Shared","общего"),("Personal","личного")):
            with self.subTest(mode=mode):
                self.lua.execute("function GetServerTime() return 12345 end")
                self.mpl.ShowDownload("Киндрих","Гордунни",None)
                window=self.mpl.downloadWindow
                request_id=window.request.split("\n")[1]
                message=mode+" API; API reset at 12650; WCL API budget is low"
                window.edit.SetText(window.edit,"MPLE1\n"+request_id+"\n"+quote(message,safe=""))
                window.edit.scripts.OnTextChanged(window.edit,True)
                self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
                self.assertIn("Сброс "+label+" API через 5 мин. 5 сек.",window.status.text)
                self.assertEqual("Перейти на личный API" in window.status.text,mode=="Shared")
                self.assertNotIn("API reset at",window.status.text)
                self.assertNotIn(mode+" API;",window.status.text)
                self.lua.execute("function GetServerTime() return 12406 end")
                window.scripts.OnUpdate(window,1)
                self.assertIn("4 мин. 4 сек.",window.status.text)
                self.lua.execute("function GetServerTime() return 13000 end")
                window.scripts.OnUpdate(window,1)
                self.assertIn("0 мин. 0 сек.",window.status.text)

    def test_diagnostic_paste_displays_readable_text_even_with_false_flag(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        edit=self.mpl.downloadWindow.edit
        edit.SetText(edit,"MPLE1\n12345-1\nConnection%20works")
        edit.scripts.OnTextChanged(edit,False)
        self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
        self.assertEqual(edit.text,self.mpl.downloadWindow.request)
        self.assertEqual(self.mpl.downloadWindow.status.text,"Connection works")

    def test_multiline_paste_waits_until_all_notifications_finish(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        edit=self.mpl.downloadWindow.edit
        partial="MPLS1\n12345-1\nMPL1\nP\teu"
        edit.SetText(edit,partial)
        edit.scripts.OnTextChanged(edit,True)
        self.assertEqual(edit.GetText(edit),partial)
        full="MPLS1\n12345-1\n"+self.body
        edit.SetText(edit,full)
        edit.scripts.OnTextChanged(edit,True)
        self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
        self.assertEqual(self.mpl.panel.profile.best,62)
        self.assertIsNone(self.mpl.pendingReply)

    def test_encoded_reply_survives_wow_tab_expansion(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        edit=self.mpl.downloadWindow.edit
        reply="MPLS1\n12345-1\nMPLB1\n"+quote(self.body,safe="")
        # Reproduce the transformation observed in the user's real EditBox.
        pasted=reply.replace("\t","    ")
        edit.SetText(edit,pasted)
        edit.scripts.OnTextChanged(edit,True)
        self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
        self.assertEqual(self.mpl.panel.profile.best,62)
        self.assertEqual(self.mpl.panel.profile.dungeons[1].name,"Den of Nalorakk")
        self.assertFalse(self.mpl.downloadWindow.shown)

    def test_download_prepares_request_automatically_and_status_check_is_honest(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        f=self.mpl.downloadWindow
        self.assertEqual(f.phase,"copy")
        self.assertIsNotNone(self.mpl.pendingReply)
        self.assertTrue(f.edit.focused)
        self.assertEqual(f.phase,"copy")
        request=f.edit.GetText(f.edit)
        self.assertTrue(request.startswith("MPLS1\n"))
        self.lua.execute("function IsControlKeyDown() return true end")
        f.edit.scripts.OnKeyUp(f.edit,"C")
        self.assertEqual(f.phase,"waiting")
        f.refresh.scripts.OnClick()
        self.assertEqual(f.edit.GetText(f.edit),request)
        self.assertIn("Ctrl+V",f.status.text)
        self.assertIsNotNone(self.mpl.pendingReply)

    def test_status_check_ignores_unrelated_clipboard_and_unwrapped_exports(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        f=self.mpl.downloadWindow
        for text in ("unrelated clipboard contents",self.body,"MPLS1\nother-id\nMPLB1\n"+quote(self.body,safe="")):
            f.edit.SetText(f.edit,text)
            f.edit.scripts.OnTextChanged(f.edit,True)
            self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
            self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)
            self.assertIsNotNone(self.mpl.pendingReply)
            self.assertTrue(f.shown)
            self.assertEqual(f.edit.GetText(f.edit),f.request)

    def test_retry_does_not_accept_reply_from_previous_request(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        f=self.mpl.downloadWindow
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        self.assertEqual(self.mpl.pendingReply.id,"12345-2")
        count,err=self.mpl.ReceiveReply("MPLS1\n12345-1\n"+self.body,True)
        self.assertIsNone(count)
        self.assertIn("другой",err)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)

    def test_receive_button_does_not_depend_on_copy_key_events(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        f=self.mpl.downloadWindow
        # No key event arrives, but the receive action must still work.
        f.refresh.scripts.OnClick()
        self.assertEqual(f.phase,"waiting")
        self.assertEqual(f.edit.GetText(f.edit),f.request)
        self.assertIn("Ctrl+V",f.status.text)

    def test_reopen_resets_progress_and_rejects_previous_reply(self):
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        f=self.mpl.downloadWindow
        request_id=self.mpl.pendingReply.id
        f.Hide(f)
        f.scripts.OnHide()
        self.mpl.ShowDownload("Киндрих","Гордунни",None)
        self.assertEqual(f.phase,"copy")
        self.assertEqual(f.edit.GetText(f.edit),f.request)
        self.assertIn("Ctrl+C",f.status.text)
        self.assertNotEqual(self.mpl.pendingReply.id,request_id)
        reply="MPLS1\n"+request_id+"\nMPLB1\n"+quote(self.body,safe="")
        f.edit.SetText(f.edit,reply)
        f.edit.scripts.OnTextChanged(f.edit,True)
        self.lua.execute("local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end")
        self.assertIsNotNone(self.mpl.pendingReply)
        self.assertEqual(len(self.lua.globals().MPlusLogsDB.profiles),0)
        self.assertIn("другой",f.status.text)


if __name__=="__main__": unittest.main()
