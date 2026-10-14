"""Offline checks. Run with bundled Python; Lua tests require lupa (Lua 5.1)."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".test-deps"))
from lupa.lua51 import LuaRuntime

def load_locales(lua, mpl, locale="ruRU"):
    lua.execute("function GetLocale() return ... end".replace("...", '"'+locale+'"'))
    files=[ROOT/"Localization.lua",ROOT/"Locales/enUS.lua"]
    files.extend(path for path in sorted((ROOT/"Locales").glob("*.lua")) if path.name!="enUS.lua")
    for path in files:
        lua.execute("return assert(loadstring(...))",path.read_text(encoding="utf-8"))("MPlusLogs",mpl)

spec = importlib.util.spec_from_file_location("wcl_sync", ROOT / "tools/wcl_sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

MOCK = r'''
local function newFrame()
    local f = {scripts={}, shown=false, lines={}, edit=false}
    local methods = {}
    function methods:CreateFontString() return newFrame() end
    function methods:CreateTexture() return newFrame() end
    function methods:SetText(text) self.text = text end
    function methods:GetText() return self.text or "" end
    function methods:SetScript(name, callback) self.scripts[name] = callback end
    function methods:HookScript(name, callback) self.scripts[name] = callback end
    function methods:Show() self.shown = true end
    function methods:Hide() self.shown = false end
    function methods:IsShown() return self.shown end
    function methods:IsVisible() local parent=rawget(self,"parent"); return self.shown and (not parent or parent:IsVisible()) end
    function methods:GetParent() return self.parent end
    function methods:GetFrameLevel() return 1 end
    function methods:SetWidth(w) self.width=w end
    function methods:GetWidth() return rawget(self,"width") or 100 end
    function methods:SetSize(w,h) self.width=w; self.height=h end
    function methods:SetPoint(point,...) self.points=rawget(self,"points") or {}; self.points[point]={...} end
    function methods:ClearAllPoints() self.points={} end
    function methods:SetFocus() self.focused=true end
    function methods:ClearFocus() self.focused=false end
    function methods:HasFocus() return self.focused==true end
    function methods:HighlightText() self.highlighted=true end
    function methods:SetHeight(h) self.height = h end
    function methods:GetHeight() return rawget(self,"height") or 208 end
    function methods:SetShown(value) self.shown=value end
    function methods:SetEnabled(value) self.enabled=value end
    function methods:Enable() self.enabled=true end
    function methods:Disable() self.enabled=false end
    function methods:SetTextColor(r,g,b) self.textColor={r,g,b} end
    function methods:SetScrollChild(child) self.child = child end
    function methods:AddLine(...) self.lines[#self.lines+1] = {...} end
    methods.AddDoubleLine = methods.AddLine
    function methods:GetUnit() return "Test", "target" end
    return setmetatable(f, {__index=function(_, k) return methods[k] or function() end end})
end
function CreateFrame(_, name, parent, template)
    local f = newFrame(); f.parent = parent
    if template=="UIPanelScrollFrameTemplate" then f.ScrollBar=newFrame() end
    if template=="LFGListColumnHeaderTemplate" then f.Label=newFrame(); f.columnTemplate=template end
    if name then _G[name] = f end
    return f
end
UIParent = newFrame()
GameTooltip = newFrame()
UISpecialFrames = {}
SlashCmdList = {}
function GetCurrentRegion() return 3 end
function GetServerTime() return 1791777600 end
function GetNormalizedRealmName() return "Гордунни" end
function UnitFullName() return "Киндрих", "Гордунни" end
function UnitExists(unit) return unit == "player" or unit == "target" end
function UnitIsPlayer() return true end
function InCombatLockdown() return combat or false end
function issecretvalue(v) return type(v) == "table" and v.secret == true end
function strtrim(text) return text:match("^%s*(.-)%s*$") end
hooks = {}
function hooksecurefunc(name, callback) hooks[name] = callback end
function LFGListApplicantMember_OnEnter() end
function LFGListSearchEntry_OnEnter() end
C_LFGList = {
    GetApplicantMemberInfo=function() return applicantName or "Киндрих-Гордунни" end,
    GetSearchResultInfo=function() return {leaderName="Киндрих-Гордунни",activityIDs={1}} end,
    GetActiveEntryInfo=function() return {activityIDs={1}} end,
    GetActivityInfoTable=function() return {categoryID=2,isMythicPlusActivity=true} end
}
Menu = {callbacks={}}
function Menu.ModifyMenu(name, callback) Menu.callbacks[name] = callback end
Enum = {TooltipDataType={Unit=1}}
TooltipDataProcessor = {}
function TooltipDataProcessor.AddTooltipPostCall(_, fn) unitTooltip = fn end
'''


def api_fixture():
    # Synthetic schema fixture, not a captured Warcraft Logs response.
    return {"data": {"characterData": {"character": {
        "id": 81818678, "name": "Киндрих", "hidden": False,
        "server": {"name": "Gordunni", "slug": "gordunni", "region": {"slug": "EU"}},
        "performance": {"bestPerformanceAverage": 62, "medianPerformanceAverage": 34,
                        "allStars": [{"points":3774}],
                        "throughputRankings":{"12825":{"best_level":19,"best_per_second_amount":168110,
                            "best_historical_percentile":62,"median_historical_percentile":34}},
                        "rankings": [{"encounter": {"id": 12825, "name": "Den of Nalorakk"},
                                      "rankPercent": 62, "medianPercent": 34, "totalKills": 27,
                                      "bestAmount": 472, "bracketData": "19"}]},
        "score": {"allStars": [{"points": 3774}], "rankings": [
            {"encounter": {"id": 12825, "name": "Den of Nalorakk"}, "bestAmount": 472}]}
    }}}}


class AddonTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.mpl = self.lua.table()
        load_locales(self.lua,self.mpl)
        self.frames = []
        for path in ("Data.lua", "Snapshot.lua", "UI.lua", "Integration.lua"):
            code = (ROOT / path).read_text(encoding="utf-8")
            self.lua.execute("return assert(loadstring(...))", code)("MPlusLogs", self.mpl)
        self.lua.execute("MPlusLogsDB = {profiles={}}")

    def test_identity_cyrillic_realm_spaces_and_snapshot(self):
        profile, name, realm = self.mpl.GetProfile("киндрих-гордунни")
        self.assertEqual(profile.runs, 162)
        self.assertEqual(len(profile.dungeons), 8)

    def test_expiry_uses_24_hours_and_formats_date(self):
        from datetime import datetime,timezone
        profile=self.lua.table_from({"updated":"2026-11-22 12:00 UTC"})
        stamp,display=self.mpl.ProfileDate(profile)
        self.assertEqual(display,"22.11.2026")
        self.assertEqual(stamp,datetime(2026,11,22,12,tzinfo=timezone.utc).timestamp())
        self.assertFalse(self.mpl.IsProfileStale(profile,stamp+24*3600-1)[0])
        self.assertTrue(self.mpl.IsProfileStale(profile,stamp+24*3600)[0])
        profile.updated="2026-02-30 12:00 UTC"
        self.assertTrue(self.mpl.IsProfileStale(profile,stamp)[0])

    def test_scrollbar_only_when_rows_overflow(self):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        panel=self.mpl.panel
        self.assertFalse(panel.scroll.ScrollBar.shown)
        panel.content.SetHeight(panel.content,300)
        self.mpl.UpdatePanelScroll(panel)
        self.assertTrue(panel.scroll.ScrollBar.shown)
        panel.content.SetHeight(panel.content,208)
        self.mpl.UpdatePanelScroll(panel)
        self.assertFalse(panel.scroll.ScrollBar.shown)

    def test_stale_notice_and_gray_text_clear_after_refresh(self):
        self.mpl.Import(self.export())
        profile,_,_=self.mpl.GetProfile("Киндрих-Гордунни",None)
        profile.updated="2026-10-09 00:00 UTC"
        self.mpl.ShowProfile("Киндрих-Гордунни")
        self.assertTrue(self.mpl.staleWindow.shown)
        self.assertIn("09.10.2026",self.mpl.staleWindow.message.text)
        self.assertIn("ff888888",self.mpl.panel.summary.text)
        self.assertAlmostEqual(self.mpl.panel.rows[1].cells[1].textColor[1],0.53)
        profile.updated="2026-10-12 03:59 UTC"
        self.mpl.ShowProfile("Киндрих-Гордунни")
        self.assertFalse(self.mpl.staleWindow.shown)
        self.assertNotIn("ff888888",self.mpl.panel.summary.text)
        self.assertEqual(self.mpl.panel.rows[1].cells[1].textColor[1],0.72)
        self.assertEqual(self.mpl.Normalize("Гор Дунни"), "гордунни")
        self.assertEqual(self.mpl.Identity("Someone-Area 52"), ("Someone", "Area 52"))

    def export(self):
        args = SimpleNamespace(realm="Гордунни", region="eu", zone=55, season="Test season",
                               spec="Guardian", metric="dps", server_slug=None)
        return sync.export(sync.normalize(api_fixture(), args))

    def test_export_import_round_trip_and_precedence(self):
        self.assertEqual(self.mpl.Import(self.export()), 1)
        profile, _, _ = self.mpl.GetProfile("Киндрих-Гордунни")
        self.assertEqual(profile.spec, "Guardian")
        self.assertEqual(profile.best, 62)
        self.assertEqual(profile.dungeons[1].amount, 168110)
        self.assertEqual(profile.dungeons[1].time, "")
        self.assertEqual(profile.dungeons[1].level, 19)

    def test_failed_import_is_atomic(self):
        self.mpl.Import(self.export())
        for bad in ("return os.execute('bad')", self.export().replace("\t62\t", "\t101\t", 1),
                    self.export().replace("\t55\t", "\t47\t", 1), self.export().removesuffix("E\n"),
                    "x" * 500001, "MPL1\n"):
            result, error = self.mpl.Import(bad)
            self.assertIsNone(result)
            self.assertTrue(error)
            self.assertEqual(self.mpl.GetProfile("Киндрих-Гордунни")[0].best, 62)

    def test_no_data_is_distinct_from_zero(self):
        self.assertIsNone(self.mpl.GetProfile("Nobody-Гордунни")[0])
        self.assertEqual(self.mpl.Percent(None), "—")
        self.assertIn("0%", self.mpl.Percent(0))

    def test_panel_snapshot_missing_and_healer(self):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        self.assertEqual(len(self.mpl.panel.rows), 8)
        self.assertIn("Снимок", self.mpl.panel.source.text)
        self.assertIn("11|r", self.mpl.panel.rows[6].cells[8].text)
        self.assertTrue(self.mpl.panel.rows[6].cells[8].text.endswith("*"))
        self.mpl.ShowProfile("Nobody-Гордунни")
        self.assertTrue(self.mpl.panel.emptyMessage.shown)
        self.assertEqual(self.mpl.panel.loadButton.text,"Загрузить M+ логи")
        self.assertFalse(self.mpl.panel.scroll.shown)
        self.assertFalse(self.mpl.panel.rows[1].shown)
        self.mpl.Import(self.export().replace("\tdps\t", "\thps\t"))
        self.mpl.ShowProfile("Киндрих-Гордунни")
        self.assertEqual(self.mpl.panel.metricHeading.text, "Лучший DPS")
        self.assertEqual(self.mpl.panel.headings[8].text,"Best %")
        self.assertEqual(self.mpl.panel.rows[1].cells[7].text,"—")

    def test_tooltip_duplicate_secret_and_combat(self):
        tooltip = self.lua.globals().GameTooltip
        self.mpl.AddTooltip(tooltip, "Киндрих-Гордунни")
        count = len(tooltip.lines)
        self.mpl.AddTooltip(tooltip, "Киндрих-Гордунни")
        self.assertEqual(len(tooltip.lines), count)
        self.mpl.AddTooltip(tooltip, self.lua.table_from({"secret": True}))
        self.assertEqual(len(tooltip.lines), count)
        self.lua.globals().combat = True
        self.mpl.AddTooltip(tooltip, "Nobody-Гордунни")
        self.assertEqual(len(tooltip.lines), count)

    def test_menu_applicant_opens_captured_character(self):
        # Fire an event to install lazy hooks, then change the candidate after menu creation.
        self.lua.execute("MPlusLogsDB={profiles={}}")
        # Integration installs menu hooks on an event; find the event frame by capturing CreateFrame.
        self.lua.execute('''
            eventFrames = {}
            local original = CreateFrame
            function CreateFrame(...) local f=original(...); eventFrames[#eventFrames+1]=f; return f end
        ''')
        self.lua.execute("return assert(loadstring(...))", (ROOT / "Integration.lua").read_text(encoding="utf-8"))("MPlusLogs", self.mpl)
        self.lua.execute('''
            eventFrames[1].scripts.OnEvent(eventFrames[1], "PLAYER_LOGIN")
            local owner = CreateFrame("Frame")
            owner.memberIdx=1; owner.parent={applicantID=123}
            local root={}
            function root:CreateDivider() end
            function root:CreateButton(_, callback) if not self.callback then self.callback=callback end end
            Menu.callbacks.MENU_LFG_FRAME_MEMBER_APPLY(owner,root)
            applicantName="Nobody-Гордунни"
            root.callback()
        ''')
        self.assertEqual(self.mpl.panel.name, "Киндрих")


class AdapterTests(unittest.TestCase):
    def args(self):
        return SimpleNamespace(realm="Гордунни", region="eu", zone=55, season="Test",
                               spec="Guardian", metric="dps", server_slug=None)

    def test_missing_values_are_not_guessed(self):
        raw = api_fixture()
        char = raw["data"]["characterData"]["character"]
        row = char["performance"]["throughputRankings"]["12825"]
        del row["best_level"]
        del row["best_historical_percentile"]
        char["performance"]["allStars"].append({"points": 1000})
        profile = sync.normalize(raw, self.args())
        self.assertIsNone(profile["score"])
        self.assertIsNone(profile["dungeons"][0]["level"])
        self.assertIsNone(profile["dungeons"][0]["best"])
        self.assertEqual(profile["dungeons"][0]["time"], "")

    def test_hidden_and_unknown_schema_fail(self):
        for change in ("hidden", "performance"):
            raw = api_fixture()
            raw["data"]["characterData"]["character"][change] = True if change == "hidden" else {}
            with self.assertRaises(ValueError):
                sync.normalize(raw, self.args())

    def test_captured_mplus_response_matches_character_page(self):
        import json
        raw=json.loads((ROOT / "experiments/wcl-points-and-damage.json").read_text(encoding="utf-8"))
        args=self.args(); args.spec=None
        profile=sync.normalize(raw,args)
        self.assertEqual(profile["runs"],162)
        self.assertAlmostEqual(profile["best"],37.375)
        self.assertAlmostEqual(profile["median"],22.375)
        first=profile["dungeons"][0]
        self.assertEqual(first["level"],19)
        self.assertAlmostEqual(first["amount"],194056.58777,places=3)
        self.assertEqual(first["best"],22)
        self.assertEqual(first["median"],20)

    def test_old_dps_only_schema_is_rejected(self):
        raw=api_fixture()
        del raw["data"]["characterData"]["character"]["performance"]["throughputRankings"]
        with self.assertRaisesRegex(ValueError,"throughputRankings"):
            sync.normalize(raw,self.args())

    def test_dual_healer_metrics_roundtrip_and_column_order(self):
        import copy
        raw=api_fixture()
        char=raw["data"]["characterData"]["character"]
        char["damage"]=copy.deepcopy(char.pop("performance"))
        char["healing"]=copy.deepcopy(char["damage"])
        char["damage"]["rankings"][0]["bestSpec"]="Holy"
        char["healing"]["bestPerformanceAverage"]=91
        t=char["healing"]["throughputRankings"]["12825"]
        t.update(best_level=14,best_per_second_amount=250000,best_historical_percentile=91,median_historical_percentile=86)
        args=self.args(); args.spec=None
        profile=sync.normalize(raw,args)
        self.assertEqual(profile["role"],"HEALER")
        self.assertEqual(profile["metric"],"hps")
        self.assertEqual(profile["dungeons"][0]["amount"],250000)
        self.assertEqual(profile["dungeons"][0]["otherAmount"],168110)
        self.assertEqual(profile["dungeons"][0]["otherLevel"],19)
        lua=LuaRuntime(unpack_returned_tuples=True); lua.execute(MOCK)
        mpl=lua.table()
        load_locales(lua,mpl)
        for path in ("Data.lua","Snapshot.lua","UI.lua"):
            lua.execute("return assert(loadstring(...))",(ROOT / path).read_text(encoding="utf-8"))("MPlusLogs",mpl)
        lua.execute("MPlusLogsDB={profiles={}}")
        self.assertEqual(mpl.Import(sync.export(profile)),1)
        mpl.ShowProfile("Киндрих-Гордунни")
        self.assertEqual(mpl.panel.metricHeading.text,"Лучший DPS")
        self.assertEqual(mpl.panel.headings[8].text,"Best %")
        row=mpl.panel.rows[1]
        self.assertEqual(row.cells[2].text,19)
        self.assertEqual(row.cells[7].text,"168.11K")
        mpl.panel.metricTabs.hps.scripts.OnClick()
        self.assertEqual(mpl.panel.metricHeading.text,"Лучший HPS")
        self.assertEqual(row.cells[2].text,14)
        self.assertEqual(row.cells[7].text,"250.00K")
        self.assertEqual(row.cells[3].text,"—")

    def test_lfg_role_overrides_historical_spec_for_order(self):
        import copy
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance")
        char["healing"]=copy.deepcopy(char["damage"])
        args=self.args(); args.role="HEALER"
        profile=sync.normalize(raw,args)
        self.assertEqual(profile["metric"],"hps")
        args.role="TANK"
        profile=sync.normalize(raw,args)
        self.assertEqual(profile["metric"],"dps")

    def test_missing_secondary_rows_are_dashes_not_zero(self):
        import copy
        for empty in ({}, [], "[]", None, "null"):
            with self.subTest(empty=empty):
                raw=api_fixture(); char=raw["data"]["characterData"]["character"]
                char["damage"]=char.pop("performance")
                char["healing"]=copy.deepcopy(char["damage"])
                char["healing"]["throughputRankings"]=empty
                profile=sync.normalize(raw,self.args())
                self.assertEqual(profile["dungeons"][0]["amount"],168110)
                self.assertIsNone(profile["dungeons"][0]["otherAmount"])
                self.assertIsNone(profile["dungeons"][0]["otherBest"])

    def test_leaderboard_only_rankings_are_no_public_logs(self):
        import copy
        for empty in ({}, [], "[]", None, "null"):
            with self.subTest(empty=empty):
                raw=api_fixture(); char=raw["data"]["characterData"]["character"]
                char["damage"]=char.pop("performance")
                char["damage"]["throughputRankings"]=empty
                char["healing"]=copy.deepcopy(char["damage"])
                with self.assertRaisesRegex(sync.NoProfile,"Публичные логи M\\+ не найдены"):
                    sync.normalize(raw,self.args())

    def test_empty_primary_keeps_available_secondary_measurements(self):
        import copy
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance")
        char["healing"]=copy.deepcopy(char["damage"])
        char["damage"]["throughputRankings"]=[]
        profile=sync.normalize(raw,self.args())
        self.assertIsNone(profile["dungeons"][0]["amount"])
        self.assertEqual(profile["dungeons"][0]["otherAmount"],168110)

    def test_secondary_throughput_rankings_accepts_json_encoded_object(self):
        import copy,json
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance")
        char["healing"]=copy.deepcopy(char["damage"])
        char["healing"]["throughputRankings"]=json.dumps(char["healing"]["throughputRankings"])
        profile=sync.normalize(raw,self.args())
        self.assertEqual(profile["dungeons"][0]["otherAmount"],168110)

    def test_malformed_secondary_throughput_rankings_reports_shape(self):
        import copy
        raw=api_fixture(); char=raw["data"]["characterData"]["character"]
        char["damage"]=char.pop("performance")
        char["healing"]=copy.deepcopy(char["damage"])
        char["healing"]["throughputRankings"]=["not", "an", "object"]
        with self.assertRaisesRegex(ValueError,"Unknown secondary throughputRankings shape"):
            sync.normalize(raw,self.args())


if __name__ == "__main__":
    unittest.main()
