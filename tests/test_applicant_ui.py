"""Native applicant log column and invitation identity checks; no real invites."""
import unittest

import test_batch
import clipboard_protocol
import realm_resolver


class ApplicantUITests(unittest.TestCase):
    setUp = test_batch.BatchTests.setUp
    players = test_batch.BatchTests.players
    fetch = test_batch.BatchTests.fetch
    flush = test_batch.BatchTests.flush

    def authorize(self):
        self.lua.execute('''
            LFGListUtil_IsEntryEmpowered=function() return true end
            C_LFGList.HasActiveEntryInfo=function() return true end
            C_LFGList.InviteApplicant=function(id) invitedID=id; inviteCalls=(inviteCalls or 0)+1 end
            GetNumGroupMembers=function() return 1 end
            IsInRaid=function() return false end
        ''')

    def test_lookup_button_and_enter_open_the_entered_character(self):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        f = self.mpl.panel
        self.assertEqual(f.headings[4].text, "Runs")
        f.lookup.SetText(f.lookup, "  Alice-Area 52  ")
        f.lookupButton.scripts.OnClick()
        self.assertEqual(f.name, "Alice")
        self.assertEqual(f.realm, "Area 52")
        self.assertEqual(f.lookup.text, "Alice-Area52")
        self.assertEqual(f.character.text, "Alice — Area 52")
        self.assertTrue(f.emptyMessage.shown)
        f.lookup.SetText(f.lookup, "Киндрих-Гордунни")
        f.lookup.scripts.OnEnterPressed()
        self.assertEqual(f.name, "Киндрих")
        self.assertTrue(f.scroll.shown)
        self.assertFalse(f.lookup.focused)

    def test_invite_rejects_temporarily_unavailable_realm(self):
        self.authorize()
        context=self.players()[1]
        self.lua.execute('''
            GetNormalizedRealmName=function() return nil end
            C_LFGList.GetApplicantMemberInfo=function() return "Alice" end
        ''')
        valid,error=self.mpl.ValidateApplicant(context)
        self.assertIsNone(valid)
        self.assertEqual(error,"Данные участника недоступны")
        self.assertIsNone(self.lua.globals().inviteCalls)

    def test_url_copy_closes_after_native_copy_and_only_for_ctrl_c(self):
        self.lua.execute("IsControlKeyDown=function() return controlDown or false end")
        self.mpl.ShowProfile("Киндрих-Гордунни")
        self.mpl.CopyURL("Киндрих", "Гордунни", self.mpl.panel.profile)
        f = self.mpl.copy
        self.assertIn("/character/id/81818678?zone=55", f.edit.text)
        f.edit.scripts.OnKeyDown(f.edit, "C")
        self.flush()
        self.assertTrue(f.shown)
        self.lua.globals().controlDown = True
        f.edit.scripts.OnKeyDown(f.edit, "A")
        self.flush()
        self.assertTrue(f.shown)
        f.edit.scripts.OnKeyDown(f.edit, "C")
        self.assertTrue(f.shown)
        self.flush()
        self.assertFalse(f.shown)
        # The mock Hide does not dispatch OnHide automatically.
        f.scripts.OnHide()
        self.assertFalse(f.edit.focused)
        self.assertTrue(self.mpl.panel.shown)

    def test_pending_url_copy_does_not_close_a_reopened_dialog(self):
        self.lua.execute("IsControlKeyDown=function() return true end")
        self.mpl.CopyURL("Alice", "Гордунни", None)
        f = self.mpl.copy
        f.edit.scripts.OnKeyDown(f.edit, "C")
        self.mpl.CopyURL("Bob", "Гордунни", None)
        self.flush()
        self.assertTrue(f.shown)
        self.assertIn("/Bob?zone=55", f.edit.text)

    def test_dungeon_row_links_follow_current_player_dungeon_and_metric(self):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        f = self.mpl.panel
        row = f.rows[1]
        row.scripts.OnMouseUp(row, "RightButton")
        self.assertIsNone(self.mpl.copy)
        row.scripts.OnMouseUp(row, "LeftButton")
        self.assertEqual(self.mpl.copy.edit.text,
                         "https://www.warcraftlogs.com/character/id/81818678?zone=55"
                         "&boss=12993&metric=points_and_damage")
        row.scoreSpecIcon.scripts.OnMouseUp(row.scoreSpecIcon, "LeftButton")
        self.assertIn("&boss=12993&", self.mpl.copy.edit.text)
        # Reuse the rendered rows for a different character and dungeon.
        f.name = "Alice"
        f.realm = "Area 52"
        f.profile = self.lua.table_from({
            "spec": "All specs", "metric": "dps", "realmSlug": "area-52",
            "dungeons": self.lua.table_from([
                self.lua.table_from({"name": "Ruby Life Pools"})])})
        f.viewMetric = "hps"
        self.mpl.RenderProfileStats(f)
        row.scripts.OnMouseUp(row, "LeftButton")
        self.assertIn("/area-52/Alice?zone=55&boss=112521&metric=points_and_healing",
                      self.mpl.copy.edit.text)
        # The generic profile button still produces the unfiltered profile URL.
        self.mpl.CopyURL(f.name, f.realm, f.profile)
        self.assertNotIn("&boss=", self.mpl.copy.edit.text)

    def test_dungeon_links_use_wcl_encounter_ids_and_ignore_unknown_dungeons(self):
        for name, encounter in (("Kings' Rest", 61762), ("Temple of Sethraliss", 61877),
                                ("Den of Nalorakk", 12825), ("Murder Row", 12813),
                                ("The Blinding Vale", 12859), ("Voidscar Arena", 12923)):
            self.assertIn(f"&boss={encounter}&", self.mpl.DungeonURL(
                "Alice", "Area 52", None, name, "dps"))
        self.assertIsNone(self.mpl.DungeonURL("Alice", "Area 52", None, "Unknown", "dps"))

    def test_invite_visible_only_with_applicant_origin_and_group_label(self):
        self.authorize()
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        f = self.mpl.panel
        self.assertTrue(f.inviteButton.shown)
        self.assertTrue(f.inviteButton.enabled)
        self.assertEqual(f.inviteButton.text, "Пригласить группу (2)")
        self.assertFalse(f.lookup.shown)
        f.inviteButton.scripts.OnClick()
        self.assertEqual(self.lua.globals().invitedID, 10)
        self.assertFalse(f.inviteButton.enabled)
        self.assertEqual(f.inviteButton.text, "Отправлено")
        self.mpl.ShowProfile("Alice", "Гордунни")
        self.assertFalse(f.inviteButton.shown)
        self.assertFalse(f.lookup.shown)
        self.assertTrue(f.searchButton.shown)

    def test_reused_id_with_new_selected_member_cannot_invite(self):
        self.authorize()
        player = self.players()[1]
        self.lua.execute('C_LFGList.GetApplicantMemberInfo=function() return "Mallory-Гордунни" end')
        ok, err = self.mpl.InviteFromProfile(player)
        self.assertIsNone(ok)
        self.assertIn("изменился", err)
        self.assertIsNone(self.lua.globals().invitedID)

    def test_changed_partner_also_blocks_invite(self):
        self.authorize()
        player = self.players()[1]
        self.lua.execute('''C_LFGList.GetApplicantMemberInfo=function(_,member)
            return (member==1 and "Alice" or "Mallory").."-Гордунни" end''')
        self.assertIsNone(self.mpl.InviteFromProfile(player)[0])
        self.assertIsNone(self.lua.globals().invitedID)

    def test_departed_or_already_invited_application_is_blocked(self):
        self.authorize()
        player = self.players()[1]
        self.lua.execute('C_LFGList.GetApplicants=function() return {} end')
        self.assertIsNone(self.mpl.InviteFromProfile(player)[0])
        self.lua.execute('''C_LFGList.GetApplicants=function() return {10} end
            C_LFGList.GetApplicantInfo=function() return {numMembers=2,applicationStatus="invited"} end''')
        self.assertIsNone(self.mpl.InviteFromProfile(player)[0])
        self.assertIsNone(self.lua.globals().invitedID)

    def test_combat_permissions_and_capacity_are_checked_again_at_click(self):
        self.authorize()
        player = self.players()[1]
        self.mpl.ShowProfile(player.name, player.realm, player)
        self.lua.execute('combat=true')
        self.mpl.panel.inviteButton.scripts.OnClick()
        self.assertIsNone(self.lua.globals().invitedID)
        self.lua.execute('combat=false; LFGListUtil_IsEntryEmpowered=function() return false end')
        self.assertIsNone(self.mpl.InviteFromProfile(player)[0])
        self.lua.execute('LFGListUtil_IsEntryEmpowered=function() return true end; GetNumGroupMembers=function() return 4 end')
        ok, err = self.mpl.InviteFromProfile(player)
        self.assertIsNone(ok)
        self.assertIn("мест", err)

    def cell(self,index):
        member=self.lua.globals().testRows[1].Members[index]
        return self.mpl.applicantLogCells[member]

    def test_column_metrics_update_and_cells_open_matching_context(self):
        self.authorize()
        self.mpl.InstallBatchButton()
        self.assertIsNone(self.mpl.applicantSidebar)
        self.assertEqual(self.cell(1).metric,"dps")
        self.assertEqual(self.cell(2).metric,"dps")
        self.assertIn("—",self.cell(1).text.text)
        _,request=self.mpl.SendBatchRequest(self.players())
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,self.fetch)
        self.assertEqual(self.mpl.ReceiveReply(response,True),1)
        self.assertIn("62%",self.cell(1).text.text)
        self.assertNotIn("/",self.cell(1).text.text)
        self.cell(2).scripts.OnClick()
        self.assertEqual(self.mpl.panel.name,"Bob")
        self.assertEqual(self.mpl.panel.applicant.memberIndex,2)
        self.assertTrue(self.mpl.panel.inviteButton.enabled)
        self.lua.execute('C_LFGList.GetApplicants=function() return {} end; C_LFGList.GetApplicantInfo=function() return {numMembers=2,applicationStatus="cancelled"} end')
        self.mpl.UpdateBatchButton()
        self.assertFalse(self.cell(1).shown)
        self.assertFalse(self.cell(2).shown)
        self.assertFalse(self.mpl.panel.inviteButton.enabled)

    def test_download_preserves_applicant_context(self):
        self.authorize()
        player = self.players()[1]
        self.mpl.ShowDownload(player.name, player.realm, None, player)
        f = self.mpl.downloadWindow
        def fetch_specs(args):
            raw=self.fetch(args)
            for metric in ('damage','healing'):
                data=raw['data']['characterData']['character'][metric]
                data['rankings'][0]['spec']=args.spec or 'Feral'
                data['rankings'][0]['bestSpec']=args.spec or 'Feral'
                data['allStars'][0]['spec']=args.spec or 'Feral'
            return raw
        response = clipboard_protocol.reply(f.request, realm_resolver.load_mappings(), self.cache, fetch_specs)
        self.assertEqual(self.mpl.ReceiveReply(response, True), (1, None))
        self.assertEqual(self.mpl.panel.applicant.applicantID, 10)
        self.assertTrue(self.mpl.panel.inviteButton.enabled)

    def test_column_uses_damage_for_damage_role_and_marks_expired_cache(self):
        self.mpl.InstallBatchButton()
        _, request = self.mpl.SendBatchRequest(self.players())
        def fetch_both(args):
            raw = self.fetch(type("Args", (), {"name": "Alice"})())
            raw["data"]["characterData"]["character"]["name"] = args.name
            raw["data"]["characterData"]["character"]["healing"]["bestPerformanceAverage"] = 88
            return raw
        response = clipboard_protocol.reply(request, realm_resolver.load_mappings(), self.cache, fetch_both)
        self.assertEqual(self.mpl.ReceiveReply(response, True), 2)
        self.assertIn("62%",self.cell(1).text.text)
        self.assertNotIn("88%",self.cell(1).text.text)
        self.mpl.ShowProfile('Alice','Гордунни')
        self.assertIn('DPS Лучший % в среднем:',self.mpl.panel.summary.text)
        self.mpl.panel.metricTabs.hps.scripts.OnClick()
        self.assertIn('HPS Лучший % в среднем:',self.mpl.panel.summary.text)
        self.assertIn('88|r',self.mpl.panel.summary.text)
        self.mpl.panel.metricTabs.dps.scripts.OnClick()
        self.mpl.AddTooltip(self.lua.globals().GameTooltip,'Alice','Гордунни')
        self.assertEqual(self.lua.globals().GameTooltip.lines[4][1],'DPS Best / Median')
        row = self.cell(2)
        self.assertEqual(row.metric,"dps")
        self.assertIn("62%",row.text.text)
        profile, _, _ = self.mpl.GetProfile("Bob", "Гордунни")
        profile.updated = "2026-10-01 00:00 UTC"
        self.mpl.UpdateBatchButton()
        self.assertIn("Обновите логи",row.detail)
        self.assertIn("ff888888",row.text.text)

    def test_recycled_native_row_does_not_keep_previous_character_percent(self):
        self.mpl.InstallBatchButton()
        _,request=self.mpl.SendBatchRequest(self.players())
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,self.fetch)
        self.mpl.ReceiveReply(response,True)
        self.assertIn("62%",self.cell(1).text.text)
        self.lua.execute('C_LFGList.GetApplicantMemberInfo=function() return "Mallory-Гордунни" end')
        # Before Blizzard redraws the recycled frame, a click cannot open Alice.
        self.cell(1).scripts.OnClick()
        self.assertIsNone(self.mpl.panel)
        self.mpl.RefreshApplicantLogs()
        self.assertIn("—",self.cell(1).text.text)
        self.assertNotIn("62",self.cell(1).text.text)

    def test_native_column_positions_and_combat_hide(self):
        self.mpl.InstallBatchButton()
        member=self.lua.globals().testRows[1].Members[1]
        self.assertEqual(member.Rating.points.CENTER[3],253)
        self.assertEqual(self.cell(1).points.LEFT[3],280)
        self.assertEqual(self.cell(1).width,56)
        self.assertEqual(member.Name.points.RIGHT[3],115)
        self.assertEqual(member.parent.width,399)
        self.assertEqual(self.lua.globals().PVEFrame.width,653)
        self.assertEqual(self.lua.globals().LFGListPVEStub.width,428)
        self.assertEqual(self.mpl.logColumn.columnTemplate,"LFGListColumnHeaderTemplate")
        self.lua.execute('combat=true')
        self.mpl.RefreshApplicantLogs()
        self.assertFalse(self.cell(1).shown)
        self.lua.execute('combat=false')
        self.mpl.RefreshApplicantLogs()
        self.assertTrue(self.cell(1).shown)

    def test_window_restores_width_after_leaving_applicants(self):
        self.mpl.InstallBatchButton()
        viewer=self.lua.globals().LFGListFrame.ApplicationViewer
        self.assertEqual(self.lua.globals().PVEFrame.width,653)

        viewer.Hide(viewer); viewer.scripts.OnHide()
        self.assertEqual(self.lua.globals().PVEFrame.width,563)
        self.assertEqual(self.lua.globals().LFGListPVEStub.width,338)
        self.assertFalse(self.mpl.logColumn.shown)
        viewer.Show(viewer); self.mpl.RefreshApplicantLogs()
        self.assertEqual(self.lua.globals().PVEFrame.width,653)
        # Repeated refreshes must not keep adding 90 pixels.
        self.mpl.RefreshApplicantLogs()
        self.assertEqual(self.lua.globals().PVEFrame.width,653)

    def mock_raider_export(self):
        self.lua.execute('''
            RaiderIO_ExportButton=CreateFrame("Button",nil,LFGListFrame)
            local b=RaiderIO_ExportButton
            b:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOM",-12,7)
            b.GetNumPoints=function() return 1 end
            b.GetPoint=function(self) return "BOTTOMRIGHT",unpack(self.points.BOTTOMRIGHT) end
        ''')

    def test_raider_export_moves_out_of_cancel_button_and_restores_on_exit(self):
        self.mock_raider_export()
        self.mpl.InstallBatchButton()
        export = self.lua.globals().RaiderIO_ExportButton
        self.assertEqual(export.points.BOTTOMRIGHT[2], 'BOTTOMRIGHT')
        self.assertEqual(export.points.BOTTOMRIGHT[3], -112)
        self.mpl.RefreshApplicantLogs(True)
        self.assertEqual(export.points.BOTTOMRIGHT[2], 'BOTTOM')
        self.assertEqual(export.points.BOTTOMRIGHT[3], -12)

    def test_raider_export_loaded_later_is_adjusted_on_next_refresh(self):
        self.mpl.InstallBatchButton()
        self.mock_raider_export()
        self.mpl.RefreshApplicantLogs()
        self.mpl.RefreshApplicantLogs()
        export = self.lua.globals().RaiderIO_ExportButton
        self.assertEqual(export.points.BOTTOMRIGHT[2], 'BOTTOMRIGHT')
        self.mpl.RefreshApplicantLogs(True)
        self.assertEqual(export.points.BOTTOMRIGHT[2], 'BOTTOM')

    def test_raider_export_scaled_anchor_rounding_does_not_block_move(self):
        self.mock_raider_export()
        self.lua.execute('RaiderIO_ExportButton:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOM",-12.000000953674,7.0000004768372)')
        self.mpl.InstallBatchButton()
        export = self.lua.globals().RaiderIO_ExportButton
        self.assertEqual(export.points.BOTTOMRIGHT[2], 'BOTTOMRIGHT')
        self.assertEqual(export.points.BOTTOMRIGHT[3], -112)
        self.lua.execute('RaiderIO_ExportButton:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOMRIGHT",-112.00000762939,7.0000004768372)')
        self.mpl.RefreshApplicantLogs(True)
        self.assertEqual(export.points.BOTTOMRIGHT[2], 'BOTTOM')

    def test_raider_export_native_reanchor_is_adjusted_again(self):
        self.mock_raider_export()
        self.mpl.InstallBatchButton()
        self.lua.execute('RaiderIO_ExportButton:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOM",-12,7)')
        self.mpl.RefreshApplicantLogs()
        self.assertEqual(self.lua.globals().RaiderIO_ExportButton.points.BOTTOMRIGHT[2], 'BOTTOMRIGHT')

    def test_custom_raider_export_position_is_preserved(self):
        self.mock_raider_export()
        self.lua.execute('RaiderIO_ExportButton:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOM",-60,7)')
        self.mpl.InstallBatchButton()
        self.assertEqual(self.lua.globals().RaiderIO_ExportButton.points.BOTTOMRIGHT[3], -60)

    def test_raider_export_does_not_move_in_combat(self):
        self.mpl.InstallBatchButton()
        self.mock_raider_export()
        self.lua.execute('combat=true')
        self.mpl.RefreshApplicantLogs()
        self.assertEqual(self.lua.globals().RaiderIO_ExportButton.points.BOTTOMRIGHT[2], 'BOTTOM')
        self.lua.execute('combat=false')
        self.mpl.RefreshApplicantLogs()
        self.assertEqual(self.lua.globals().RaiderIO_ExportButton.points.BOTTOMRIGHT[2], 'BOTTOMRIGHT')

    def test_raider_export_external_move_is_not_overwritten_on_exit(self):
        self.mock_raider_export()
        self.mpl.InstallBatchButton()
        self.lua.execute('RaiderIO_ExportButton:SetPoint("BOTTOMRIGHT",LFGListFrame,"BOTTOMRIGHT",-160,7)')
        self.mpl.RefreshApplicantLogs(True)
        self.assertEqual(self.lua.globals().RaiderIO_ExportButton.points.BOTTOMRIGHT[3], -160)

    def test_panel_switch_restores_width_even_before_old_viewer_visibility_changes(self):
        self.mpl.InstallBatchButton()
        viewer=self.lua.globals().LFGListFrame.ApplicationViewer
        self.assertEqual(viewer.InfoBackground.width,428)

        self.assertEqual(viewer.DescriptionFrame.width,400)
        # Native OnHide can run during the panel transition. Force restoration
        # while activePanel/visibility still describe the outgoing viewer.
        viewer.scripts.OnHide()
        self.assertEqual(self.lua.globals().PVEFrame.width,563)
        self.assertEqual(self.lua.globals().LFGListPVEStub.width,338)
        self.assertEqual(viewer.InfoBackground.width,338)
        self.assertFalse(self.cell(1).shown)
        # The post-hook also restores when switching to another panel.
        self.lua.execute('LFGListFrame.activePanel=CreateFrame("Frame")')
        self.mpl.RefreshApplicantLogs()
        self.assertEqual(self.lua.globals().PVEFrame.width,563)
        self.assertFalse(self.mpl.logColumn.shown)
        self.lua.execute('LFGListFrame.activePanel=LFGListFrame.ApplicationViewer')
        self.mpl.RefreshApplicantLogs()
        self.assertEqual(viewer.InfoBackground.width,428)

    def test_delisting_restores_fractional_width_before_panel_switch(self):
        self.mpl.InstallBatchButton()
        # Real WoW dimensions have floating point rounding after UI scaling.
        self.lua.execute('''
            PVEFrame.width=653.0000610351562
            LFGListPVEStub.width=428.0000305175781
            C_LFGList.HasActiveEntryInfo=function() return false end
        ''')
        self.mpl.RefreshApplicantLogs()
        self.assertEqual(self.lua.globals().PVEFrame.width,563)
        self.assertEqual(self.lua.globals().LFGListPVEStub.width,338)
        self.assertFalse(self.mpl.logColumn.expanded)
        self.assertFalse(self.mpl.logColumn.shown)
        self.assertFalse(self.cell(1).shown)


if __name__ == "__main__":
    unittest.main()
