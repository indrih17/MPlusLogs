"""Party/applicant tabs and one shared Companion exchange."""
import unittest

import test_batch
import clipboard_protocol
import realm_resolver


class GroupProfileTests(unittest.TestCase):
    setUp = test_batch.BatchTests.setUp
    players = test_batch.BatchTests.players
    fetch = test_batch.BatchTests.fetch
    flush = test_batch.BatchTests.flush

    def party(self):
        self.lua.execute('''
            UnitExists=function(unit) return unit=="player" or unit:match("^party[1-4]$")~=nil end
            UnitFullName=function(unit)
                return unit=="player" and "Alice" or "Member"..unit:sub(-1),"Гордунни"
            end
            UnitGroupRolesAssigned=function(unit) return unit=="player" and "HEALER" or "DAMAGER" end
            IsInRaid=function() return false end
        ''')

    def test_slash_opens_five_tabs_including_self_and_one_batch(self):
        self.party()
        self.lua.globals().SlashCmdList.MPLUSLOGS("")
        f = self.mpl.panel
        self.assertEqual(len(f.groupPlayers), 5)
        self.assertEqual(len(f.playerTabs), 5)
        self.assertEqual(f.name, "Alice")
        self.assertEqual(len(self.mpl.pendingReply.players), 5)
        self.assertIn("MPLQ2\n", self.mpl.downloadWindow.request)
        f.playerTabs[4].scripts.OnClick()
        self.assertEqual(f.name, "Member3")
        self.assertEqual(len(f.groupPlayers), 5)
        self.assertFalse(f.inviteButton.shown)

    def test_applicant_group_keeps_clicked_member_and_only_its_application(self):
        self.mpl.ShowProfile("Bob", "Гордунни", self.players()[2])
        f = self.mpl.panel
        self.assertEqual(f.name, "Bob")
        self.assertEqual(len(f.groupPlayers), 2)
        self.assertEqual(f.groupPlayers[1].memberIndex, 1)
        f.playerTabs[1].scripts.OnClick()
        self.assertEqual(f.name, "Alice")
        self.assertEqual(f.applicant.memberIndex, 1)
        self.assertEqual(f.applicant.applicantID, 10)

    def test_batch_reply_refreshes_selected_tab_and_keeps_hidden_member(self):
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        f = self.mpl.panel
        f.playerTabs[2].scripts.OnClick()
        request = self.mpl.downloadWindow.request
        response = clipboard_protocol.reply(request, realm_resolver.load_mappings(), self.cache, self.fetch)
        self.assertEqual(self.mpl.ReceiveReply(response, True), 1)
        self.assertEqual(f.name, "Bob")
        self.assertEqual(len(f.groupPlayers), 2)
        self.assertIn("скрыты", f.footer.text)
        f.playerTabs[1].scripts.OnClick()
        self.assertEqual(f.name, "Alice")
        self.assertTrue(f.scroll.shown)
        self.assertEqual(f.profile.metric, "hps")

    def test_fresh_profiles_skip_download_and_unrelated_lookup_clears_tabs(self):
        self.lua.execute('''
            MPlusLogs.FilterFreshProfiles=function() return {},2 end
        ''')
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.downloadWindow)
        f = self.mpl.panel
        self.mpl.ShowProfile("Other", "Гордунни")
        self.assertFalse(f.playerTabs[1].shown)
        self.assertFalse(f.playerTabs[2].shown)

    def test_old_batch_reply_does_not_reopen_group_after_manual_lookup(self):
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        request = self.mpl.downloadWindow.request
        self.mpl.ShowProfile("Other", "Гордунни")
        response = clipboard_protocol.reply(request, realm_resolver.load_mappings(), self.cache, self.fetch)
        self.mpl.ReceiveReply(response, True)
        self.assertEqual(self.mpl.panel.name, "Other")
        self.assertFalse(self.mpl.panel.playerTabs[1].shown)

    def test_request_filters_fresh_member_but_keeps_both_tabs(self):
        self.lua.execute('''
            MPlusLogsDB.profiles[MPlusLogs.Key("Alice","Гордунни")]={
                updated="2026-10-12 04:00 UTC",metric="hps",dual=true,spec="All specs"}
        ''')
        self.mpl.ShowProfile("Bob", "Гордунни", self.players()[2])
        self.assertEqual(len(self.mpl.panel.groupPlayers), 2)
        self.assertEqual(len(self.mpl.pendingReply.players), 1)
        self.assertEqual(self.mpl.pendingReply.players[1].name, "Bob")

    def test_spec_refresh_preserves_group_tabs_without_new_request(self):
        self.mpl.ShowProfile("Alice", "Гордунни", self.players()[1])
        request_id = self.mpl.pendingReply.id
        self.mpl.ShowProfile("Alice", "Гордунни", self.mpl.panel.applicant, True)
        self.assertEqual(len(self.mpl.panel.groupPlayers), 2)
        self.assertEqual(self.mpl.pendingReply.id, request_id)
        self.assertTrue(self.mpl.panel.playerTabs[2].shown)

    def test_party_skips_unavailable_and_duplicate_identity(self):
        self.party()
        self.lua.execute('''
            UnitFullName=function(unit)
                if unit=="party4" then return nil end
                if unit=="party3" then return "Alice","Гордунни" end
                return unit=="player" and "Alice" or unit,"Гордунни"
            end
        ''')
        self.assertEqual(len(self.mpl.CollectParty()), 3)


if __name__ == "__main__":
    unittest.main()
