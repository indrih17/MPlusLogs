"""Cached group profiles stay readable; optional healing and rescan are explicit."""
import unittest
import test_name_search
import clipboard_protocol
import realm_resolver
import test_primary_metric
import build_database as builder
import wcl_sync as wcl


class CachedDisplayTests(unittest.TestCase):
    setUp = test_name_search.NameSearchTests.setUp
    response = test_name_search.NameSearchTests.response

    def seed_stale(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        profile, _, _ = self.mpl.GetProfile('Frákkie', 'Draenor')
        profile.updated = '2026-10-01 00:00 UTC'
        self.mpl.searchGroupWindow.players[1].loaded = None
        return profile

    def test_stale_known_profile_is_visible_with_date_while_exchange_is_pending(self):
        self.seed_stale()
        self.mpl.ShowSearchGroupLogs(10)
        panel = self.mpl.panel
        self.assertTrue(panel.profile)
        self.assertTrue(panel.scroll.shown)
        self.assertIn('01.10.2026', panel.source.text)
        self.assertTrue(panel.staleBanner.shown)
        self.assertFalse(self.mpl.searchGroupWindow.players[1].loaded)
        self.assertTrue(self.mpl.downloadWindow.shown)
        self.assertEqual(self.mpl.downloadWindow.phase, 'copy')

    def test_unknown_realm_cannot_display_same_name_from_fallback_realm(self):
        self.seed_stale()
        player = self.mpl.searchGroupWindow.players[1]
        player.realm = None
        self.mpl.panel.groupPlayers = None
        self.mpl.OpenSearchGroupProfile(1)
        self.assertFalse(self.mpl.panel.profile)
        self.assertFalse(self.mpl.panel.scroll.shown)

    def test_hidden_state_prevents_cached_display(self):
        self.seed_stale()
        self.lua.execute('''
            local MPL=...
            MPL.profileStates={[MPL.Key("Frákkie","Draenor")]={reason="hidden"}}
        ''', self.mpl)
        self.mpl.OpenSearchGroupProfile(1)
        self.assertFalse(self.mpl.panel.profile)
        self.assertFalse(self.mpl.panel.scroll.shown)

    def test_optional_hps_needs_explicit_load_and_uses_single_metric_request(self):
        profile = self.seed_stale()
        profile.dual = False
        profile.metric = 'dps'
        self.mpl.ShowProfile('Frákkie', 'Draenor', None, True)
        panel = self.mpl.panel
        panel.metricTabs.hps.scripts.OnClick()
        self.assertIsNone(self.mpl.downloadWindow)
        self.assertEqual(panel.loadButton.text, self.mpl.L['Load HPS'])
        panel.loadButton.scripts.OnClick()
        exchange = self.mpl.downloadWindow
        self.assertEqual(exchange.requestedMetric, 'hps')
        self.assertFalse(exchange.batch)
        _, body = clipboard_protocol.unwrap_request(exchange.request)
        self.assertIn('\thps\t', body)
        self.assertTrue(panel.profile)
        self.assertTrue(panel.scroll.shown)
        panel.metricTabs.dps.scripts.OnClick()
        self.assertNotEqual(panel.loadButton.text, self.mpl.L['Load HPS'])

    def test_explicit_rescan_includes_fresh_inferred_members_with_empty_realm(self):
        self.mpl.ReceiveSearchGroupReply(self.response())
        self.mpl.searchGroupWindow.onlyMissing = True
        _, request = self.mpl.BeginSearchGroupRequest(True)
        self.assertIn(',rescan', request)
        member = self.mpl.searchGroupWindow.requestPlayers[2]
        self.assertIsNone(member.realm)
        self.assertEqual(member.origin, 'search')
        self.assertEqual(len(self.mpl.searchGroupWindow.requestPlayers), 2)

    def test_partial_import_then_explicit_hps_load_imports_full_profile_and_keeps_view(self):
        self.lua.execute('local MPL=...; MPL.companionInfo={capabilities={primarymetric=true}}', self.mpl)
        args = builder.arguments(dict(name='Киндрих', realm='Гордунни', server_slug='gordunni',
                                      region='eu', role='DAMAGER'))
        partial = wcl.normalize(test_primary_metric.raw_profile(partial=True), args)
        self.assertEqual(self.mpl.Import(wcl.export(partial)), 1)
        self.mpl.RecordApplicant('Киндрих-Гордунни', 'DAMAGER', 63, 'MAGE')
        self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        panel = self.mpl.panel
        self.assertTrue(panel.profile.dual)
        self.assertTrue(panel.profile.secondaryPending)
        self.assertEqual(panel.profile.metric, 'dps')
        damage = panel.rows[1].cells[7].text
        self.assertNotIn(damage, ('—', '0'))
        panel.metricTabs.hps.scripts.OnClick()
        self.assertIsNone(self.mpl.downloadWindow)
        self.assertEqual(panel.rows[1].cells[7].text, '—')
        self.assertIn('HPS', panel.loadButton.text)
        panel.loadButton.scripts.OnClick()
        exchange = self.mpl.downloadWindow
        calls = []
        def fetch(request_args):
            calls.append(request_args)
            return test_primary_metric.raw_profile()
        reply = clipboard_protocol.reply(exchange.request, realm_resolver.load_mappings(), self.cache, fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].metric, 'hps')
        exchange.edit.SetText(exchange.edit, reply)
        exchange.edit.scripts.OnTextChanged(exchange.edit, True)
        self.lua.execute('local pending=timers; timers={}; for _,fn in ipairs(pending) do fn() end')
        self.assertEqual(exchange.phase, 'done')
        self.assertFalse(exchange.shown)
        self.assertEqual(panel.viewMetric, 'hps')
        self.assertTrue(panel.profile.dual)
        self.assertFalse(panel.profile.secondaryPending)
        self.assertEqual(panel.profile.role, 'DAMAGER')
        self.assertEqual(panel.profile.metric, 'dps')
        self.assertEqual(panel.rows[1].cells[7].text, damage)
        self.assertNotIn(self.mpl.L['Load HPS'], panel.loadButton.text)

    def test_damage_role_remains_damage_with_historical_guardian_spec(self):
        args = builder.arguments(dict(name='Киндрих', realm='Гордунни', server_slug='gordunni',
                                      region='eu', role='DAMAGER'))
        partial = wcl.normalize(test_primary_metric.raw_profile(class_id=11, partial=True), args)
        self.assertEqual(partial['primarySpec'], 'Guardian')
        self.assertEqual(self.mpl.Import(wcl.export(partial)), 1)
        self.mpl.RecordApplicant('Киндрих-Гордунни', 'DAMAGER', None, 'DRUID')
        self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        panel = self.mpl.panel
        self.assertEqual(panel.profile.primarySpec, 'Guardian')
        self.assertEqual(panel.profile.role, 'DAMAGER')
        self.assertEqual(self.mpl.ProfileRole(panel.profile), 'DAMAGER')
        panel.metricTabs.hps.scripts.OnClick()
        self.assertIn('HPS', panel.loadButton.text)

    def test_legacy_healing_only_profile_offers_damage_load(self):
        profile = self.seed_stale()
        profile.dual = False
        profile.metric = 'hps'
        self.mpl.ShowProfile('Frákkie', 'Draenor', None, True)
        panel = self.mpl.panel
        panel.metricTabs.dps.scripts.OnClick()
        self.assertIn('DPS', panel.loadButton.text)
        self.assertIn('DPS', panel.footer.text)
        panel.loadButton.scripts.OnClick()
        self.assertEqual(self.mpl.downloadWindow.requestedMetric, 'dps')


if __name__ == '__main__':
    unittest.main()
