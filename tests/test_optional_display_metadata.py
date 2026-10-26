"""Mixed helpers keep loading logs and persist accurate, nonblocking notices."""
import unittest
from unittest.mock import patch

import clipboard_protocol
import test_addon
import test_rank_percent_protocol as rank_protocol
import test_profile_layout
import test_name_search
import realm_resolver
from test_localization import LOCALES


class OptionalDisplayMetadataTests(unittest.TestCase):
    def setUp(self):
        rank_protocol.RankPercentProtocolTests.setUp(self)
        self.lua.execute('C_Timer={After=function() end}')

    raw = rank_protocol.RankPercentProtocolTests.raw
    exchange = rank_protocol.RankPercentProtocolTests.exchange
    supports = rank_protocol.RankPercentProtocolTests.supports

    def receive(self, old=False, batch=False):
        if old:
            self.supports(False)
        if batch:
            _, request = self.mpl.SendBatchRequest(self.lua.table_from([
                dict(name='Киндрих', realm='Гордунни', role='TANK')], recursive=True))
        else:
            _, request = self.mpl.SendRequest('Киндрих', 'Гордунни', 'dps', 'All specs')
        capabilities = clipboard_protocol.CAPABILITIES - ({'rankcolors'} if old else set())
        with patch.object(clipboard_protocol, 'CAPABILITIES', capabilities):
            reply = self.exchange(request, self.raw(True))
        result = self.mpl.ReceiveReply(reply, True)
        self.assertEqual(result[0] if isinstance(result, tuple) else result, 1)
        return self.mpl.GetProfile('Киндрих', 'Гордунни')[0]

    def test_old_helper_single_and_batch_load_numbers_and_persist_warning_after_reopen(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                self.supports(None)
                profile = self.receive(old=True, batch=batch)
                self.assertEqual(profile.displayMetadata, 'companion')
                self.assertEqual(profile.dungeons[1].rank, 3248)
                self.assertEqual(profile.specRanks[1].rank, 48)
                self.assertIsNone(profile.dungeons[1].rankPercent)
                self.mpl.panel.Hide(self.mpl.panel)
                self.mpl.companionInfo = None
                self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
                panel = self.mpl.panel
                self.assertTrue(panel.staleBanner.shown)
                self.assertIn(self.mpl.L['Некоторые данные отсутствуют. Обновите MPlusLogs Companion.'],
                              panel.staleBanner.message.text)

    def test_discovery_allows_immediate_cached_refresh_then_removes_warning(self):
        self.supports(False)
        profile = self.receive()
        self.assertEqual(profile.displayMetadata, 'refresh')
        self.lua.execute('GetServerTime=function() return MPlusLogs.ProfileDate(MPlusLogs.panel.profile) end')
        self.assertGreater(self.mpl.ProfileRefreshRemaining(profile), 0)
        self.assertEqual(self.mpl.UpdateProfileLoadButton(), (False, 0))
        self.mpl.panel.loadButton.scripts.OnClick()
        window = self.mpl.downloadWindow
        self.assertTrue(window.shown)
        self.assertFalse(window.refresh)
        self.assertIn('rankcolors', window.request)
        self.assertEqual(self.mpl.ReceiveReply(self.exchange(window.request, self.raw(True)), True), (1, None))
        profile = self.mpl.GetProfile('Киндрих', 'Гордунни')[0]
        self.assertEqual(profile.displayMetadata, 'complete')
        self.assertFalse(self.mpl.panel.staleBanner.shown)
        self.assertGreater(self.mpl.ProfileRefreshRemaining(profile), 0)

    def test_staleness_and_missing_fields_share_banner_without_overlap(self):
        self.supports(None)
        profile = self.receive(old=True)
        panel = self.mpl.panel
        panel.stale = True
        self.mpl.RenderProfileStats(panel)
        self.assertIn(self.mpl.L['Данные устарели'], panel.staleBanner.message.text)
        self.assertIn('MPlusLogs Companion', panel.staleBanner.message.text)
        self.assertIn('\n', panel.staleBanner.message.text)
        self.assertGreaterEqual(panel.staleBanner.height, 42)
        offset = panel.staleBanner.height + 4
        self.assertEqual(panel.height, 656 + offset)
        self.assertEqual(panel.tableHeader.points.TOPLEFT[2], -254 - offset)
        self.assertEqual(panel.scroll.points.TOPLEFT[2], -294 - offset)
        self.supports(True)
        self.assertIn(self.mpl.L['Некоторые данные отсутствуют. Обновите логи.'],
                      self.mpl.ProfileDisplayWarning(profile))

    def test_missing_wcl_percentile_with_supported_transport_is_not_a_companion_error(self):
        self.supports(True)
        raw = self.raw(True)
        for metric in ('damage', 'healing'):
            stars = raw['data']['characterData']['character'][metric]
            stars['rankings'][0]['allStars'].pop('rankPercent')
            stars['allStars'][0].pop('rankPercent')
        _, request = self.mpl.SendRequest('Киндрих', 'Гордунни', 'dps', 'All specs')
        self.assertEqual(self.mpl.ReceiveReply(self.exchange(request, raw), True), (1, None))
        profile = self.mpl.GetProfile('Киндрих', 'Гордунни')[0]
        self.assertIsNone(profile.dungeons[1].rankPercent)
        self.assertEqual(profile.displayMetadata, 'complete')
        self.assertIsNone(self.mpl.ProfileDisplayWarning(profile))

    def test_existing_saved_api_profile_warns_without_another_exchange(self):
        self.supports(None)
        profile = self.receive(old=True)
        profile.displayMetadata = None
        self.mpl.companionInfo = None
        self.mpl.panel.Hide(self.mpl.panel)
        self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        self.assertIn('MPlusLogs Companion', self.mpl.panel.staleBanner.message.text)
        self.assertTrue(self.mpl.panel.staleBanner.shown)
        self.supports(True)
        self.assertIn(self.mpl.L['Некоторые данные отсутствуют. Обновите логи.'],
                      self.mpl.ProfileDisplayWarning(profile))

    def test_complete_legacy_display_fields_do_not_trigger_migration_warning(self):
        self.supports(True)
        profile = self.receive()
        profile.displayMetadata = None
        self.assertIsNotNone(profile.dungeons[1].rankPercent)
        self.assertIsNone(self.mpl.ProfileDisplayWarning(profile))

    def test_warning_wraps_and_reserves_measured_height_in_all_locales(self):
        for locale in LOCALES:
            with self.subTest(locale=locale):
                lua, mpl = test_profile_layout.ProfileLayoutTests().runtime(locale)
                panel = mpl.panel
                panel.profile.displayMetadata = 'companion'
                panel.stale = True
                mpl.companionInfo = None
                # Simulate a narrow locale wrapping its second warning line.
                panel.staleBanner.message.GetStringHeight = lua.eval('function() return 56 end')
                mpl.RenderProfileStats(panel)
                self.assertEqual(panel.staleBanner.height, 70)
                self.assertEqual(panel.staleBanner.message.height, 56)
                self.assertEqual(panel.tableHeader.points.TOPLEFT[2], -328)
                self.assertIn(mpl.L['Некоторые данные отсутствуют. Обновите MPlusLogs Companion.'],
                              panel.staleBanner.message.text)


class SearchDisplayMetadataTests(unittest.TestCase):
    setUp = test_name_search.NameSearchTests.setUp

    def test_cached_metadata_refresh_keeps_search_context_and_all_member_tabs(self):
        self.mpl.BeginSearchGroupRequest()
        first = self.mpl.searchGroupWindow.request
        self.assertIn('rankcolors', first)
        client = test_name_search.Client()
        reply = clipboard_protocol.reply(first, realm_resolver.load_mappings(), self.cache, client)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply), 2)
        before = self.mpl.panel.searchMember
        self.assertEqual(self.mpl.panel.profile.displayMetadata, 'complete')
        self.assertFalse(self.mpl.panel.staleBanner.shown)
        # Exercise migration of a previously loaded limited profile as well.
        for player in self.mpl.searchGroupWindow.players.values():
            self.mpl.GetProfile(player.name,player.realm)[0].displayMetadata = 'refresh'
        self.mpl.panel.loadButton.scripts.OnClick()
        request = self.mpl.downloadWindow.request
        self.assertIn('rankcolors', request)
        self.assertEqual(len(self.mpl.searchGroupWindow.requestPlayers), 2)
        client.calls.clear()
        reply = clipboard_protocol.reply(request, realm_resolver.load_mappings(), self.cache, client)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply), 2)
        self.assertEqual(client.calls, [])
        self.assertTrue(self.lua.eval('function(a,b) return a==b end')(before, self.mpl.panel.searchMember))
        self.assertEqual(len(self.mpl.panel.searchPlayers), 2)
        self.assertEqual(self.mpl.panel.profile.displayMetadata, 'complete')
        self.assertFalse(self.mpl.panel.staleBanner.shown)


if __name__ == '__main__':
    unittest.main()
