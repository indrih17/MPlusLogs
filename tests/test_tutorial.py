"""The guide follows the real user flow without changing live addon state."""
import re
import unittest

import test_screenshot_transport as transport_fixture

ROOT = transport_fixture.ROOT
STEP_IDS = ("companion", "applicants", "exchange", "quick-read", "profile",
            "dungeon", "search", "party", "settings")
LOCALES = ("enUS", "ruRU", "deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "zhCN", "zhTW")
PROTECTED = re.compile(r"Ctrl\+[CV]|/mpl(?: (?:tutorial|settings))?|N/M|%d")


class TutorialTests(unittest.TestCase):
    def setUp(self):
        transport_fixture.ReplyTests.setUp(self)
        self.lua.execute('''
            MPlusLogsDB={profiles={}}
            createdFrames={}
            local create=CreateFrame
            function CreateFrame(kind,...)
                local frame=create(kind,...)
                local inherited=getmetatable(frame).__index
                -- Real frames return nil for absent addon-owned fields. Keep
                -- the shared mock's no-op fallback for unimplemented API calls.
                setmetatable(frame,{__index=function(self,key)
                    if key:match("^[a-z]") then return nil end
                    return inherited(self,key)
                end})
                frame.kind=kind; frame.shown=true
                createdFrames[#createdFrames+1]=frame
                function frame:HookScript(name,callback)
                    local previous=self.scripts[name]
                    self.scripts[name]=function(...)
                        if previous then previous(...) end
                        callback(...)
                    end
                end
                function frame:Show()
                    local changed=not self.shown
                    self.shown=true
                    if changed and self.scripts.OnShow then self.scripts.OnShow(self) end
                end
                function frame:Hide()
                    local changed=self.shown
                    self.shown=false
                    if changed and self.scripts.OnHide then self.scripts.OnHide(self) end
                end
                function frame:SetScale(scale) self.scale=scale end
                function frame:GetVerticalScroll() return self.verticalScroll or 0 end
                function frame:SetChecked(value) self.checked = value end
                function frame:GetChecked() return self.checked == true end
                function frame:SetVerticalScroll(offset)
                    local changed=offset~=(self.verticalScroll or 0)
                    self.verticalScroll=offset
                    if changed and self.scripts.OnVerticalScroll then
                        self.scripts.OnVerticalScroll(self,offset)
                    end
                end
                local fontString=frame.CreateFontString
                function frame:CreateFontString(...)
                    local field=fontString(self,...)
                    field.parent=self; field.fontSize=12; field.shown=true
                    function field:GetFont() return "FixtureLocaleFont",self.fontSize,"" end
                    function field:SetFont(file,size,flags) self.fontSize=size end
                    function field:GetStringHeight()
                        if not numericFontMetrics then return nil end
                        local lines=math.max(1,math.ceil(#self:GetText()*self.fontSize*0.55/self:GetWidth()))
                        return lines*(self.fontSize+4)
                    end
                    return field
                end
                return frame
            end
            UIParent:SetSize(1920,1080)
            function IsControlKeyDown() return controlHeld or false end
        ''')
        self.load("Settings.lua")
        self.load("TutorialSteps.lua")
        for name in sorted((ROOT/"Locales/Tutorial").glob("*.lua")):
            self.load(name.relative_to(ROOT))
        self.load("Tutorial.lua")

    def load(self, name):
        self.lua.execute("return assert(loadstring(...))", (ROOT/name).read_text(encoding="utf-8"))(
            "MPlusLogs", self.mpl)

    def raw(self, table, key):
        return self.lua.eval("rawget")(table, key)

    def same(self, first, second):
        return self.lua.eval("rawequal")(first, second)

    def click(self, button):
        button.scripts.OnClick(button)

    def show(self, step=None):
        self.mpl.ShowTutorial()
        window=self.mpl.tutorialWindow
        if step is not None and step != window.step:
            self.click(window.stepButtons[step])
        return window

    def settings_fixture(self):
        self.lua.execute('''
            SettingsPanel=CreateFrame("Frame")
            SettingsPanel:Hide()
            SettingsPanel:SetScript("OnHide",function() settingsHidden=(settingsHidden or 0)+1 end)
            Settings={OpenToCategory=function(id)
                openedCategory=id
                SettingsPanel:Show()
            end}
            local MPL=...
            MPL.settingsCategory={GetID=function() return 42 end}
        ''', self.mpl)
        return self.lua.globals().SettingsPanel

    def open_action(self, action):
        if action == "settings":
            self.settings_fixture()
            window=self.show(9)
        else:
            window=self.show(1)
        self.click(window.action)
        other=self.lua.globals().SettingsPanel if action == "settings" else self.mpl.copy
        return window,other

    def test_copy_has_stable_user_flow_ids_and_complete_localized_chapters(self):
        english=self.mpl.GetTutorialCopy("enUS")
        supported=set(re.findall(r"([a-z]{2}[A-Z]{2})=true",(ROOT/"Localization.lua").read_text(encoding="utf-8")))
        self.assertEqual(set(LOCALES),supported)
        for locale in LOCALES+("enGB", "unknownLocale"):
            with self.subTest(locale=locale):
                copy=self.mpl.GetTutorialCopy(locale)
                self.assertEqual(set(copy.keys()),set(english.keys()))
                self.assertIsNone(copy.imagePending)
                if locale in LOCALES and locale != "enUS":
                    self.assertFalse(self.same(copy,english))
                    self.assertNotEqual(copy.title,english.title)
                for key in english.keys():
                    if key != "steps":
                        self.assertTrue(copy[key].strip())
                        self.assertEqual(sorted(PROTECTED.findall(copy[key])),sorted(PROTECTED.findall(english[key])))
                self.assertEqual(tuple(copy.steps[index].id for index in range(1,10)), STEP_IDS)
                self.assertEqual(len({step.id for step in copy.steps.values()}), 9)
                for index in range(1,10):
                    step=copy.steps[index]
                    source=english.steps[index]
                    self.assertEqual(set(step.keys()),set(source.keys()))
                    for field in ("shortTitle", "title", "intro", "location", "result", "pitfall"):
                        self.assertTrue(step[field].strip())
                        self.assertEqual(sorted(PROTECTED.findall(step[field])),sorted(PROTECTED.findall(source[field])),(locale,step.id,field))
                    self.assertEqual(len(step.instructions),len(source.instructions))
                    for instruction in range(1,len(source.instructions)+1):
                        self.assertTrue(step.instructions[instruction].strip())
                        self.assertEqual(sorted(PROTECTED.findall(step.instructions[instruction])),
                                         sorted(PROTECTED.findall(source.instructions[instruction])),(locale,step.id,instruction))
                self.assertEqual(copy.steps[1].action,"download")
                self.assertEqual(copy.steps[9].action,"settings")
        self.assertTrue(self.same(self.mpl.GetTutorialCopy("unknownLocale"),
                                  self.mpl.GetTutorialCopy("enUS")))

    def test_every_chapter_renders_in_russian_english_and_fallback(self):
        for locale in LOCALES+("enGB", "unknownLocale"):
            with self.subTest(locale=locale):
                self.setUp()
                self.mpl.locale=locale
                window=self.show()
                copy=self.mpl.GetTutorialCopy(locale)
                for index in range(1,10):
                    step=copy.steps[index]
                    self.assertEqual(window.step,index)
                    self.assertEqual(window.heading.text,step.title)
                    self.assertEqual(window.body.text,step.intro)
                    self.assertIn(step.location,window.location.text)
                    self.assertEqual(window.result.text,step.result)
                    self.assertEqual(window.pitfall.text,step.pitfall)
                    self.assertEqual(window.instructions[1].text,"1. "+step.instructions[1])
                    self.assertEqual(window.action.shown,step.action is not None)
                    self.assertIn(str(index),window.progress.text)
                    self.assertIn("9",window.progress.text)
                    self.click(window.next)
                self.assertFalse(window.shown)
                self.assertEqual(self.lua.globals().MPlusLogsDB.tutorialCompletedVersion,2)

    def test_settings_chapter_explains_appearance_entry_preview_and_commit(self):
        for locale, words in (
            ("ruRU", ("Оформление", "шапке профиля", "стиль", "палитру", "шрифты", "столбцы", "предпросмотре", "Сохранить", "Отмена")),
            ("enUS", ("Appearance", "profile header", "style", "palette", "fonts", "columns", "preview", "Save", "Cancel")),
        ):
            with self.subTest(locale=locale):
                self.mpl.locale=locale
                window=self.show(9)
                chapter=self.mpl.GetTutorialCopy(locale).steps[9]
                guidance=" ".join(chapter.instructions.values())
                for word in words:
                    self.assertIn(word,guidance)
                self.assertIn("оформление" if locale=="ruRU" else "appearance",chapter.shortTitle.lower())
                self.assertEqual(len(chapter.instructions),6)
                self.assertEqual(window.instructions[2].text,"2. "+chapter.instructions[2])

    def test_bulk_loading_is_early_and_explicitly_located_above_applicants(self):
        copy=self.mpl.GetTutorialCopy("ruRU")
        stage=copy.steps[2]
        self.assertEqual(stage.id,"applicants")
        self.assertIn("над списком заявок",stage.location)
        self.assertIn("Загрузить логи всех",stage.instructions[2])
        self.assertIn("N/M",stage.pitfall)
        self.assertIn("Ctrl+C",copy.steps[3].instructions[1])
        self.assertIn("Ctrl+V",copy.steps[3].instructions[3])

    def test_no_prior_use_state_can_schedule_an_automatic_guide(self):
        self.assertIsNone(self.mpl.RequestTutorial)
        for state in ("", "tutorialCompletedVersion=1", "tutorialCompletedVersion=2",
                      "tutorialDismissedVersion=2", "companionReplySeen=true",
                      "companionIntroDismissed=true", 'profiles={old={source="WCL API: legacy fixture"}}'):
            with self.subTest(state=state):
                self.lua.execute("MPlusLogsDB={"+state+"}")
                self.assertFalse(self.mpl.TryPendingTutorial())
                self.assertIsNone(self.mpl.tutorialWindow)

    def test_manual_help_is_available_regardless_of_companion_history(self):
        for state in ("companionReplySeen=true", "companionIntroDismissed=true",
                      'profiles={old={source="WCL API: legacy fixture"}}'):
            with self.subTest(state=state):
                self.lua.execute("MPlusLogsDB={"+state+"}")
                self.mpl.ShowTutorial("companion")
                self.assertTrue(self.mpl.tutorialWindow.shown)
                self.assertEqual(self.mpl.tutorialWindow.step,1)
                self.mpl.tutorialWindow.Hide(self.mpl.tutorialWindow)

    def test_contents_jump_and_back_next_save_stable_progress(self):
        window=self.show()
        self.assertFalse(window.back.enabled)
        self.click(window.stepButtons[5])
        db=self.lua.globals().MPlusLogsDB
        self.assertEqual(db.tutorialStepId,"profile")
        self.assertEqual(db.tutorialProgressVersion,2)
        self.click(window.back)
        self.assertEqual(window.step,4)
        self.click(window.next)
        self.assertEqual(window.step,5)
        self.assertGreater(window.stepButtons[5].caption.textColor[1],
                           window.stepButtons[4].caption.textColor[1])

    def test_close_preserves_progress_without_completing_or_confirming_companion(self):
        window=self.show(6)
        self.click(window.later)
        db=self.lua.globals().MPlusLogsDB
        self.assertFalse(window.shown)
        self.assertEqual(db.tutorialDismissedVersion,2)
        self.assertEqual(db.tutorialStepId,"dungeon")
        self.assertIsNone(db.tutorialCompletedVersion)
        self.assertIsNone(db.companionReplySeen)
        self.assertIsNone(db.companionIntroDismissed)
        self.assertFalse(self.mpl.TryPendingTutorial())
        self.mpl.ShowTutorial()
        self.assertTrue(window.shown)
        self.assertEqual(window.step,6)

    def test_registered_escape_close_and_module_reload_keep_progress(self):
        window=self.show(7)
        self.assertIn("MPlusLogsTutorialWindow",tuple(self.lua.globals().UISpecialFrames.values()))
        window.Hide(window)
        self.mpl.tutorialWindow=None
        self.load("Tutorial.lua")
        self.mpl.ShowTutorial()
        self.assertEqual(self.mpl.tutorialWindow.step,7)
        self.assertEqual(self.lua.globals().MPlusLogsDB.tutorialStepId,"search")

    def test_unknown_or_old_progress_starts_at_first_chapter(self):
        for version,step in ((1,"profile"),(2,"removed-chapter")):
            with self.subTest(version=version,step=step):
                self.lua.execute("MPlusLogsDB={profiles={}}")
                db=self.lua.globals().MPlusLogsDB
                db.tutorialProgressVersion=version; db.tutorialStepId=step
                self.assertEqual(self.show().step,1)

    def test_finish_clears_progress_and_replay_can_resume_while_rereading(self):
        window=self.show(9)
        self.click(window.next)
        db=self.lua.globals().MPlusLogsDB
        self.assertEqual(db.tutorialCompletedVersion,2)
        self.assertIsNone(db.tutorialDismissedVersion)
        self.assertIsNone(db.tutorialStepId)
        self.assertIsNone(db.tutorialProgressVersion)
        self.assertFalse(self.mpl.TryPendingTutorial())
        self.mpl.ShowTutorial()
        self.assertEqual(window.step,1)
        self.click(window.stepButtons[4])
        window.Hide(window)
        self.mpl.ShowTutorial()
        self.assertEqual(window.step,4)

    def test_combat_end_without_a_manual_request_never_opens_the_guide(self):
        self.lua.execute("combat=true")
        self.assertIsNone(self.mpl.tutorialWindow)
        self.assertFalse(self.mpl.TryPendingTutorial())
        self.lua.execute("combat=false")
        self.assertFalse(self.mpl.TryPendingTutorial())
        self.assertIsNone(self.mpl.tutorialWindow)

    def test_context_help_opens_its_chapter_while_generic_help_resumes_progress(self):
        self.mpl.ShowTutorial("exchange")
        window=self.mpl.tutorialWindow
        self.assertEqual(window.step,3)
        window.Hide(window)
        self.mpl.ShowTutorial()
        self.assertEqual(window.step,3)
        self.mpl.ShowTutorial("profile")
        self.assertEqual(window.step,5)

    def test_manual_reopen_ignores_dismissal_and_waits_for_combat(self):
        window=self.show(5)
        self.click(window.later)
        self.lua.execute("combat=true")
        self.assertFalse(self.mpl.ShowTutorial())
        self.assertFalse(window.shown)
        self.lua.execute("combat=false")
        self.assertTrue(self.mpl.TryPendingTutorial())
        self.assertTrue(window.shown)
        self.assertEqual(window.step,5)

    def test_deferred_context_help_keeps_its_chapter_only_while_source_is_open(self):
        for closed in (False,True):
            with self.subTest(closed=closed):
                self.setUp()
                source=self.lua.globals().CreateFrame("Frame")
                self.lua.execute("combat=true")
                self.assertFalse(self.mpl.ShowTutorial("exchange",source))
                if closed:
                    source.Hide(source)
                self.lua.execute("combat=false")
                self.assertEqual(self.mpl.TryPendingTutorial(),not closed)
                self.assertFalse(self.mpl.TryPendingTutorial())
                if closed:
                    self.assertIsNone(self.mpl.tutorialWindow)
                else:
                    self.assertEqual(self.mpl.tutorialWindow.step,3)

    def test_reading_guide_preserves_live_profiles_request_options_and_panel(self):
        self.lua.execute('''
            local MPL=...
            MPL.panel={sentinel=true}; savedPanel=MPL.panel
            MPlusLogsDB.profiles={Alice={sentinel=42}}; savedProfiles=MPlusLogsDB.profiles
            MPlusLogsDB.options={percentile="median"}; savedOptions=MPlusLogsDB.options
        ''',self.mpl)
        self.mpl.SendRequest("Alice","Area 52","dps","")
        self.lua.globals().savedRequest=self.mpl.pendingReply
        self.lua.execute('''
            local MPL=...
            local function forbidden() error("Guide called a live action") end
            MPL.SendRequest=forbidden; MPL.SendBatchRequest=forbidden
            MPL.ShowDownload=forbidden; MPL.ShowProfile=forbidden
            MPL.ShowTutorialProfile=forbidden; MPL.SelectSpec=forbidden
        ''',self.mpl)
        window=self.show()
        for index in (9,2,8,3,7,4,6,5,1):
            self.click(window.stepButtons[index])
        self.click(window.later)
        self.assertTrue(self.lua.eval('''function(MPL)
            return MPL.panel==savedPanel and MPL.pendingReply==savedRequest
                and MPlusLogsDB.profiles==savedProfiles and savedProfiles.Alice.sentinel==42
                and MPlusLogsDB.options==savedOptions and savedOptions.percentile=="median"
                and not MPlusLogsDB.companionReplySeen
        end''')(self.mpl))

    def test_new_context_click_replaces_a_suspended_chapter_waiting_for_combat_end(self):
        window,settings=self.open_action("settings")
        self.lua.execute("combat=true")
        settings.Hide(settings)
        source=self.lua.globals().CreateFrame("Frame")
        self.assertFalse(self.mpl.ShowTutorial("exchange",source))
        self.lua.execute("combat=false")
        self.assertTrue(self.mpl.TryPendingTutorial())
        self.assertEqual(window.step,3)
        self.assertFalse(self.mpl.TryPendingTutorial())

    def test_guide_has_no_fake_exercises_or_edit_controls(self):
        window=self.show()
        for index in range(1,10):
            self.click(window.stepButtons[index])
        for field in ("demoEdit", "demoChecks", "demoBatch", "previewMenu", "groupButtons"):
            self.assertIsNone(self.raw(window,field))
        kinds={frame.kind for frame in self.lua.globals().createdFrames.values()}
        self.assertNotIn("EditBox",kinds)
        checks=[frame for frame in self.lua.globals().createdFrames.values() if frame.kind == "CheckButton"]
        self.assertEqual(len(checks),1)
        self.assertTrue(self.same(checks[0],window.hideOnFinish))

    def test_final_hide_checkbox_saves_only_when_finishing(self):
        window=self.show(1)
        self.assertFalse(window.hideOnFinish.shown)
        self.click(window.stepButtons[9])
        self.assertTrue(window.hideOnFinish.shown)
        self.assertFalse(window.hideOnFinish.GetChecked(window.hideOnFinish))
        window.hideOnFinish.SetChecked(window.hideOnFinish,True)
        self.click(window.back)
        self.assertFalse(window.hideOnFinish.shown)
        self.click(window.stepButtons[9])
        self.assertTrue(window.hideOnFinish.GetChecked(window.hideOnFinish))
        self.assertFalse(self.mpl.GetOption('hideTutorial'))
        self.click(window.later)
        self.assertFalse(self.mpl.GetOption('hideTutorial'))
        self.mpl.ShowTutorial('settings')
        self.assertFalse(window.hideOnFinish.GetChecked(window.hideOnFinish))
        window.hideOnFinish.SetChecked(window.hideOnFinish,True)
        self.click(window.next)
        self.assertTrue(self.mpl.GetOption('hideTutorial'))
        self.assertEqual(self.lua.globals().MPlusLogsDB.tutorialCompletedVersion,2)
        self.assertFalse(window.shown)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionIntroDismissed)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.companionReplySeen)
        self.mpl.ShowTutorial('settings')
        self.assertTrue(window.hideOnFinish.GetChecked(window.hideOnFinish))
        window.hideOnFinish.SetChecked(window.hideOnFinish,False)
        self.click(window.next)
        self.assertFalse(self.mpl.GetOption('hideTutorial'))

    def test_actual_download_link_suspends_and_preserves_copy_dialog_hide_handler(self):
        window,other=self.open_action("download")
        self.assertTrue(other.shown)
        self.assertIn("MPlusLogs-Companion-Setup.exe",other.edit.text)
        self.assertFalse(window.shown)
        self.assertTrue(self.same(window.suspendedFor,other))
        revision=other.revision
        other.Hide(other)
        self.assertEqual(other.revision,revision+1)
        self.assertFalse(other.edit.focused)
        self.assertTrue(window.shown)
        self.assertEqual(window.step,1)
        self.assertIsNone(self.raw(window,"suspendedFor"))
        self.assertIsNone(self.lua.globals().MPlusLogsDB.tutorialDismissedVersion)

    def test_actual_settings_action_resumes_same_chapter_without_duplicate_hooks(self):
        window,other=self.open_action("settings")
        self.assertEqual(self.lua.globals().openedCategory,42)
        for count in (1,2):
            self.assertFalse(window.shown)
            other.Hide(other)
            self.assertEqual(self.lua.globals().settingsHidden,count)
            self.assertTrue(window.shown)
            self.assertEqual(window.step,9)
            self.assertIsNone(self.lua.globals().MPlusLogsDB.tutorialDismissedVersion)
            if count == 1:
                self.click(window.action)

    def test_actions_cannot_open_external_windows_in_combat(self):
        settings=self.settings_fixture()
        window=self.show()
        self.lua.execute("combat=true")
        self.click(window.action)
        self.assertIsNone(self.mpl.copy)
        self.click(window.stepButtons[9])
        self.click(window.action)
        self.assertFalse(settings.shown)
        self.assertTrue(window.shown)

    def test_settings_link_is_localized_and_opens_guide_despite_completed_onboarding(self):
        for locale in LOCALES:
            with self.subTest(locale=locale):
                self.setUp()
                self.mpl.locale=locale
                settings=self.settings_fixture()
                settings.Show(settings)
                self.lua.execute('''
                    MPlusLogsDB.tutorialCompletedVersion=2
                    MPlusLogsDB.tutorialDismissedVersion=2
                    MPlusLogsDB.companionReplySeen=true
                    tutorialLink={Button=CreateFrame("Button")}
                    MPlusLogsTutorialLinkMixin.Init(tutorialLink)
                ''')
                link=self.lua.globals().tutorialLink
                self.assertEqual(link.Button.text,self.mpl.GetTutorialCopy().openGuide)
                self.assertFalse(self.mpl.TryPendingTutorial())
                self.click(link.Button)
                self.assertFalse(settings.shown)
                self.assertTrue(self.mpl.tutorialWindow.shown)
                self.assertEqual(self.mpl.tutorialWindow.step,1)
                self.lua.globals().MPlusLogsTutorialLinkMixin.Release(link)
                self.assertIsNone(link.Button.scripts.OnClick)

    def test_settings_link_returns_from_suspended_guide_and_defers_during_combat(self):
        for combat in (False,True):
            with self.subTest(combat=combat):
                self.setUp()
                window,settings=self.open_action("settings")
                self.lua.execute('''
                    tutorialLink={Button=CreateFrame("Button")}
                    MPlusLogsTutorialLinkMixin.Init(tutorialLink)
                ''')
                self.lua.globals().combat=combat
                self.click(self.lua.globals().tutorialLink.Button)
                self.assertFalse(settings.shown)
                self.assertEqual(window.shown,not combat)
                self.assertIsNone(self.raw(window,"suspendedFor"))
                if combat:
                    self.assertFalse(self.mpl.TryPendingTutorial())
                    self.lua.execute("combat=false")
                    self.assertTrue(self.mpl.TryPendingTutorial())
                    self.assertFalse(self.mpl.TryPendingTutorial())
                self.assertTrue(window.shown)
                self.assertEqual(window.step,9)
                self.assertIsNone(self.lua.globals().MPlusLogsDB.tutorialDismissedVersion)

    def test_download_and_settings_resume_only_after_combat(self):
        for action in ("download","settings"):
            with self.subTest(action=action):
                self.setUp()
                window,other=self.open_action(action)
                self.lua.execute("combat=true")
                other.Hide(other)
                self.assertFalse(window.shown)
                self.assertFalse(self.mpl.TryPendingTutorial())
                self.lua.execute("combat=false")
                self.assertTrue(self.mpl.TryPendingTutorial())
                self.assertTrue(window.shown)
                self.assertEqual(window.step,1 if action == "download" else 9)
                self.assertIsNone(self.lua.globals().MPlusLogsDB.tutorialDismissedVersion)

    def test_manual_reopen_cancels_stale_suspended_window_callbacks(self):
        for action in ("download","settings"):
            with self.subTest(action=action):
                self.setUp()
                window,other=self.open_action(action)
                self.lua.execute("combat=true")
                other.Hide(other)
                self.lua.execute("combat=false")
                self.mpl.ShowTutorial()
                self.click(window.stepButtons[2])
                self.assertFalse(self.mpl.TryPendingTutorial())
                other.Show(other); other.Hide(other)
                self.assertTrue(window.shown)
                self.assertEqual(window.step,2)

    def test_guide_uses_location_cards_without_screenshot_placeholders(self):
        window=self.show()
        for index in range(1,10):
            self.click(window.stepButtons[index])
            self.assertEqual(window.locationLabel.text,self.mpl.GetTutorialCopy().locationLabel)
            self.assertEqual(window.location.text,self.mpl.GetTutorialCopy().steps[index].location)
            self.assertTrue(self.same(window.location.GetParent(window.location),window.locationCard))
        for field in ("imagePending","screenshot","illustration"):
            self.assertIsNone(self.raw(window,field))

    def test_navigating_to_shorter_chapter_hides_previous_extra_instructions(self):
        window=self.show(5)
        self.assertTrue(window.instructions[4].shown)
        self.click(window.stepButtons[2])
        self.assertFalse(window.instructions[4].shown)

    def test_down_arrow_only_appears_at_top_of_overflowing_chapter(self):
        self.lua.execute("UIParent:SetSize(1024,600); numericFontMetrics=true")
        window=self.show()
        self.assertGreater(window.content.height,window.scroll.height)
        self.assertTrue(window.scrollHint.shown)

        window.scroll.scripts.OnMouseWheel(window.scroll,-1)
        self.assertFalse(window.scrollHint.shown)
        # Dragging the native scrollbar also dispatches OnVerticalScroll.
        window.scroll.SetVerticalScroll(window.scroll,0)
        self.assertTrue(window.scrollHint.shown)
        window.scroll.SetVerticalScroll(window.scroll,1)
        self.assertFalse(window.scrollHint.shown)
        self.click(window.stepButtons[9])
        self.assertEqual(window.scroll.verticalScroll,0)
        self.assertTrue(window.scrollHint.shown)

        content_height=window.content.height
        window.content.SetHeight(window.content,window.scroll.height)
        window.scroll.scripts.OnScrollRangeChanged(window.scroll,0,0)
        self.assertFalse(window.scrollHint.shown)
        window.content.SetHeight(window.content,content_height)
        window.scroll.scripts.OnScrollRangeChanged(window.scroll,0,content_height-window.scroll.height)
        self.assertTrue(window.scrollHint.shown)
        window.scroll.SetHeight(window.scroll,content_height+1)
        window.scroll.scripts.OnSizeChanged(window.scroll)
        self.assertFalse(window.scrollHint.shown)

    def test_small_screens_scroll_readable_content_and_keep_selected_sidebar_item_visible(self):
        for width,height in ((1024,600),(900,600),(800,450)):
            with self.subTest(width=width,height=height):
                self.setUp()
                self.lua.execute("UIParent:SetSize(...)",width,height)
                self.lua.execute("numericFontMetrics=true")
                window=self.show()
                self.assertLessEqual(window.width*window.scale,width-32)
                self.assertLessEqual(window.height*window.scale,height-48)
                self.assertGreaterEqual(window.body.fontSize,16)
                self.assertTrue(self.same(window.next.GetParent(window.next),window))
                self.assertTrue(self.same(window.action.GetParent(window.action),window))
                self.assertGreater(window.action.points.BOTTOMLEFT[2],0)
                self.assertTrue(self.same(window.scroll.child,window.content))
                for index in (9,1,8,2):
                    self.click(window.stepButtons[index])
                    top=(index-1)*50
                    self.assertLessEqual(window.sidebar.verticalScroll,top)
                    self.assertGreaterEqual(window.sidebar.verticalScroll+window.sidebar.height,top+44)
                    self.assertTrue(window.scroll.ScrollBar.shown)
                    window.scroll.scripts.OnMouseWheel(window.scroll,-10000)
                    self.assertEqual(window.scroll.verticalScroll,window.content.height-window.scroll.height)
                    window.scroll.scripts.OnMouseWheel(window.scroll,10000)
                    self.assertEqual(window.scroll.verticalScroll,0)
                self.click(window.stepButtons[3])
                self.assertEqual(window.scroll.verticalScroll,0)


if __name__ == "__main__":
    unittest.main()
