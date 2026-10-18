"""Opt-in bulk import uses real saved identities and the normal clipboard path."""
import unittest

import test_batch
from test_addon import ROOT
import clipboard_protocol
import realm_resolver
import wcl_sync as wcl
import build_database as builder


class ImportTestTests(unittest.TestCase):
    def setUp(self):
        self.case = test_batch.BatchTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.lua, self.mpl = self.case.lua, self.case.mpl
        self.lua.execute('return assert(loadstring(...))', (ROOT / 'ImportTest.lua').read_text(encoding='utf-8'))('MPlusLogs', self.mpl)

    def seed(self, count):
        profiles = []
        for index in range(count):
            entry = dict(name='Player' + chr(97 + index // 26) + chr(97 + index % 26),
                         realm='Гордунни', region='eu', server_slug='gordunni')
            profile = wcl.normalize(self.case.fetch(builder.arguments(entry)), builder.arguments(entry))
            # Freshness must not prevent the opt-in test exchange.
            profile['updated'] = '2026-10-12 04:00 UTC'
            profiles.append(profile)
        body = 'MPL1\n' + ''.join(wcl.export(p).removeprefix('MPL1\n') for p in profiles)
        self.assertEqual(self.mpl.Import(body), count)

    def test_selects_unique_current_region_characters_across_saved_and_bundle(self):
        self.seed(120)
        self.mpl.snapshots = self.lua.table()
        self.lua.execute('''
            local MPL=...
            MPL.bundled={}; MPL.bundledSpecs={}
            for key,p in pairs(MPlusLogsDB.profiles) do MPL.bundled[key]=p end
            MPlusLogsDB.profiles.other={name="Other",realm="Thrall",region="us",zone=55}
            MPlusLogsDB.profiles.old={name="Old",realm="Гордунни",region="eu",zone=54}
            MPL.profileStates={[MPL.Key("Playeraa","Гордунни") ]={reason="hidden"}}
        ''', self.mpl)
        players, total = self.mpl.SampleImportTestPlayers()
        self.assertEqual(total, 119)
        self.assertEqual(len(players), 100)
        names = {p.name for p in players.values()}
        self.assertEqual(len(names), 100)
        self.assertNotIn('Playeraa', names)
        self.assertTrue(all(p.spec == '' for p in players.values()))

    def test_small_and_empty_database_counts_are_honest(self):
        # Snapshot data is a valid final source when no imported profiles exist.
        self.mpl.snapshots = self.lua.table()
        players, total = self.mpl.SampleImportTestPlayers()
        self.assertEqual((len(players), total), (0, 0))
        self.seed(3)
        players, total = self.mpl.SampleImportTestPlayers()
        self.assertEqual((len(players), total), (3, 3))

    def test_oldest_first_uses_latest_known_update_per_character(self):
        self.seed(120)
        self.mpl.snapshots = self.lua.table()
        self.lua.execute('''
            local MPL=...
            for _,p in pairs(MPlusLogsDB.profiles) do p.updated="2026-10-10 04:00 UTC" end
            local a=MPlusLogsDB.profiles[MPL.Key("Playeraa","Гордунни")]
            a.updated="2026-10-01 04:00 UTC"
            local recent={}; for key,value in pairs(a) do recent[key]=value end
            recent.updated="2026-10-17 04:00 UTC"
            MPL.bundled={recent}
            MPlusLogsDB.profiles[MPL.Key("Playerab","Гордунни")].updated="Unknown"
            MPlusLogsDB.profiles[MPL.Key("Playerac","Гордунни")].updated="2026-10-02 04:00 UTC"
        ''', self.mpl)
        players, total = self.mpl.SampleImportTestPlayers()
        self.assertEqual((len(players), total), (100, 120))
        self.assertEqual(players[1].name, 'Playerab')
        self.assertEqual(players[2].name, 'Playerac')
        self.assertNotIn('Playeraa', {p.name for p in players.values()})
        again, _ = self.mpl.SampleImportTestPlayers()
        self.assertEqual([p.name for p in players.values()], [p.name for p in again.values()])

    def test_fresh_100_players_round_trip_and_timing_report(self):
        self.seed(100)
        self.lua.globals().SlashCmdList.MPLUSLOGS('testimport')
        test_window = self.mpl.importTestWindow
        self.assertTrue(test_window.shown)
        test_window.start.scripts.OnClick()
        f = self.mpl.downloadWindow
        self.assertTrue(f.importTest)
        self.assertEqual(len(self.mpl.pendingReply.players), 100)
        self.assertTrue(self.mpl.pendingReply.refresh)
        self.assertIn('refresh', f.request)
        response = clipboard_protocol.reply(f.request, realm_resolver.load_mappings(), self.case.cache, self.case.fetch)
        self.lua.execute('testClock=1000; debugprofilestop=function() return testClock end; IsControlKeyDown=function() return true end')
        f.edit.scripts.OnKeyDown(f.edit, 'V')
        self.lua.globals().testClock = 1250
        f.edit.SetText(f.edit, response[:1])
        f.edit.scripts.OnTextChanged(f.edit, True)
        self.lua.eval('function(edit,body) for i=1,#body do edit.scripts.OnChar(edit,body:sub(i,i)) end end')(f.edit,response)
        self.case.flush()
        self.case.flush()
        result = self.mpl.lastImportTest
        self.assertEqual(result.count, 100)
        self.assertEqual(result.textChangedMs, 250)
        self.assertEqual(result.bytes, len(response.encode()))
        checksum=0
        for byte in response.encode():checksum=(checksum*31+byte)%2147483647
        self.assertEqual(result.checksum,checksum)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertTrue(test_window.shown)
        self.assertIn('100', test_window.result.text)

    def test_does_not_replace_another_pending_exchange_or_start_in_combat(self):
        self.seed(2)
        self.mpl.SendRequest('Alice', 'Гордунни', 'dps', '')
        request_id = self.mpl.pendingReply.id
        self.mpl.ShowImportTest()
        self.assertEqual(self.mpl.pendingReply.id, request_id)
        self.assertIsNone(self.mpl.importTestWindow)
        self.mpl.pendingReply = None
        self.lua.globals().combat = True
        self.mpl.ShowImportTest()
        self.assertIsNone(self.mpl.importTestWindow)

    def test_replays_existing_response_repeatedly_without_sending_a_request(self):
        players=self.lua.table_from([self.lua.table_from(dict(name='Alice',realm='Гордунни',spec=''))])
        _,request=self.mpl.SendBatchRequest(players)
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.case.cache,self.case.fetch)
        self.mpl.pendingReply=None
        self.mpl.ShowImportTest()
        for no_letter_count in (False,True,False):
            self.mpl.ShowImportReplay(no_letter_count)
            f=self.mpl.downloadWindow
            self.assertEqual(f.phase,'waiting')
            self.assertEqual(f.request,'')
            self.assertIsNone(self.mpl.pendingReply)
            f.edit.SetText(f.edit,response)
            f.edit.scripts.OnTextChanged(f.edit,True)
            self.case.flush()
            self.assertEqual(self.mpl.lastImportTest.count,1)
            self.assertEqual(self.mpl.lastImportTest.noLetterCount,no_letter_count)
            self.assertIsNone(self.mpl.pendingReply)

    def test_character_capture_reassembles_reply_while_native_field_stays_tiny(self):
        players=self.lua.table_from([self.lua.table_from(dict(name='Alice',realm='Гордунни',spec=''))])
        _,request=self.mpl.SendBatchRequest(players)
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.case.cache,self.case.fetch)
        self.mpl.pendingReply=None
        self.mpl.ShowImportTest()
        self.mpl.ShowImportReplay(False,True)
        f=self.mpl.downloadWindow
        self.assertTrue(f.importTest.captureChars)
        # Model the engine dispatching characters even after its one-byte
        # display buffer fills. This native behavior still needs the live test.
        f.edit.SetText(f.edit,response[:1])
        f.edit.scripts.OnTextChanged(f.edit,True)
        self.lua.eval('function(edit,body) for i=1,#body do edit.scripts.OnChar(edit,body:sub(i,i)) end end')(f.edit,response)
        self.assertIsNone(self.mpl.lastImportTest)
        self.case.flush()
        self.case.flush()
        self.assertEqual(self.mpl.lastImportTest.count,1)
        self.assertEqual(self.mpl.lastImportTest.bytes,len(response.encode()))
        self.assertTrue(self.mpl.lastImportTest.captureChars)
        self.assertIsNone(self.mpl.pendingReply)


if __name__ == '__main__':
    unittest.main()
