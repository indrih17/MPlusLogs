"""Specialization discovery completion survives a successful one-spec reply.

Exercises real Companion envelopes and Lua import/menu rendering. Frame mocks
do not establish actual WoW glyph coverage or keyboard/menu behavior.
"""
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

import test_spec_profiles as specs


class SpecDiscoveryStateTests(unittest.TestCase):
    transport = specs.SpecProfileTests.transport

    def setUp(self):
        mock = specs.test_addon.MOCK.replace('function methods:Disable() self.enabled=false end',
            'function methods:Disable() self.enabled=false end\n    function methods:IsEnabled() return self.enabled~=false end')
        with specs.patch.object(specs.test_addon, 'MOCK', mock):
            specs.SpecProfileTests.setUp(self)
        self.transport()
        self.mpl.companionInfo = self.lua.table_from({'capabilities': {'lazyspecs': True}}, recursive=True)
        self.lua.execute('now=GetServerTime(); function GetServerTime() return now end')

    @staticmethod
    def raw(available=('Guardian',)):
        raw = specs.api_fixture()
        performance = raw['data']['characterData']['character']['performance']
        performance['allStars'] = [{'spec': spec, 'points': 3774, 'rank': 100} for spec in available]
        performance['rankings'][0]['bestSpec'] = available[0]
        return raw

    def exchange(self, include=True, spec='All specs', metric='dps', raw=None):
        raw = self.raw() if raw is None else raw
        calls = []
        def fetch(args):
            calls.append(args.spec)
            return raw
        _, request = self.mpl.SendRequest('Киндрих', 'Гордунни', metric, spec, None, include)
        with tempfile.TemporaryDirectory(dir=specs.ROOT, prefix='.test-work-') as directory:
            with specs.patch.object(specs.builder.time, 'time', return_value=self.lua.globals().now):
                reply = specs.clipboard_protocol.reply(request, {'eu': {'гордунни': 'gordunni'}}, Path(directory), fetch)
            self.assertEqual(self.mpl.ReceiveReply(reply, True), (1, None))
        return calls

    def state(self, metric='dps', name='Киндрих', realm='Гордунни'):
        return self.mpl.SpecDiscoveryState(name, realm, metric)

    def menu_action(self):
        panel = self.mpl.panel
        if panel.specMenu:
            panel.specMenu.Hide(panel.specMenu)
        panel.specButton.scripts.OnClick(panel.extraLogsButton)
        actions = [entry for entry in panel.specMenu.entries.values() if entry.kind == 'button']
        self.assertEqual(len(actions), 1)
        return actions[0]

    def test_success_with_only_main_spec_does_not_offer_another_active_discovery(self):
        calls = self.exchange()
        self.assertEqual(calls, [None])
        self.assertEqual(self.state(), 'complete')
        self.assertEqual(list(self.mpl.ProfileSpecs('Киндрих', 'Гордунни').values()), ['Guardian'])
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['No other specializations found'])
        self.assertFalse(action.button.enabled)
        action.button.scripts.OnClick(action.button)
        self.assertIsNone(self.mpl.pendingReply)
        self.assertIsNone(self.mpl.downloadWindow)

    def test_multiple_available_specs_do_not_imply_target_profiles_are_loaded(self):
        self.exchange(raw=self.raw(('Guardian', 'Feral')))
        self.assertEqual(self.state(), 'complete')
        self.assertEqual(set(self.mpl.ProfileSpecs('Киндрих', 'Гордунни').values()), {'Guardian', 'Feral'})
        self.assertIsNone(self.mpl.GetProfile('Киндрих', 'Гордунни', 'Feral')[0])
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['Specialization list loaded'])
        self.assertFalse(action.button.enabled)
        caption = self.mpl.SpecLabel('Feral', self.mpl.panel['class'])
        radio = next(entry for entry in self.mpl.panel.specMenu.entries.values()
                     if entry.kind == 'radio' and entry.text.startswith(caption))
        self.assertIn(self.mpl.L[' — not loaded'], radio.text)

    def test_ordinary_reply_and_manual_import_do_not_claim_discovery(self):
        self.exchange(include=False)
        self.assertIsNone(self.state())
        self.assertIsNone(self.lua.globals().MPlusLogsDB.specDiscoveries)
        self.mpl.Import(specs.SpecProfileTests.export(self))
        self.assertIsNone(self.state())

    def test_check_survives_variant_load_and_data_reload_then_expires(self):
        self.exchange()
        key = self.mpl.Key('Киндрих', 'Гордунни')
        record = self.lua.globals().MPlusLogsDB.specDiscoveries[key].dps
        self.assertEqual(record.checkedAt, self.lua.globals().now)
        self.assertEqual(record.updated, self.mpl.panel.profile.updated)
        self.exchange(include=False, spec='Feral', raw=self.raw(('Feral',)))
        self.assertEqual(self.state(), 'complete')
        self.lua.execute('return assert(loadstring(...))', (specs.ROOT/'Data.lua').read_text(encoding='utf-8'))('MPlusLogs', self.mpl)
        self.assertEqual(self.state(), 'complete')
        self.mpl.SetOption('freshHours', 6)
        self.lua.globals().now += 6*3600-1
        self.assertEqual(self.state(), 'complete')
        self.lua.globals().now += 1
        self.assertEqual(self.state(), 'stale')

    def test_pending_is_scoped_to_character_metric_and_discovery_request(self):
        self.mpl.SendRequest('Киндрих', 'Гордунни', 'dps', 'All specs', None, True)
        self.assertEqual(self.state(), 'pending')
        self.assertIsNone(self.state('hps'))
        self.assertIsNone(self.state(name='Other'))
        self.mpl.pendingReply = None
        self.assertIsNone(self.state())
        self.mpl.SendRequest('Киндрих', 'Гордунни', 'dps', 'Guardian', None, True)
        self.assertIsNone(self.state())

    def test_metric_checks_are_preserved_independently_and_zone_isolated(self):
        raw = self.raw()
        character = raw['data']['characterData']['character']
        character['damage'] = character.pop('performance')
        character['healing'] = specs.copy.deepcopy(character['damage'])
        self.exchange(metric='dps', raw=raw)
        self.assertEqual(self.state('dps'), 'complete')
        self.assertIsNone(self.state('hps'))
        self.exchange(metric='hps', raw=raw)
        self.assertEqual(self.state('hps'), 'complete')
        self.assertEqual(self.state('dps'), 'complete')
        self.mpl.zone = 56
        self.assertIsNone(self.state())
        self.mpl.zone = 55
        self.assertEqual(self.state(), 'complete')

    def test_errors_rejected_replies_and_targeted_include_specs_do_not_mark_complete(self):
        request_id, _ = self.mpl.SendRequest('Киндрих', 'Гордунни', 'dps', 'All specs', None, True)
        count, _ = self.mpl.ReceiveReply('MPLE1\n'+request_id+'\n'+quote('Unknown zoneRankings JSON shape'), True)
        self.assertIsNone(count)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.specDiscoveries)
        count, _ = self.mpl.ReceiveReply('MPLS1\nwrong-request\nMPL1\n', True)
        self.assertIsNone(count)
        self.assertIsNone(self.lua.globals().MPlusLogsDB.specDiscoveries)
        self.mpl.pendingReply = None
        self.exchange(include=True, spec='Guardian')
        self.assertIsNone(self.state())

    def test_actual_menu_action_requests_discovery_and_preserves_selected_variant(self):
        self.exchange(include=False, spec='Guardian')
        self.mpl.SelectSpec('Киндрих', 'Гордунни', 'Guardian')
        self.mpl.ShowProfile('Киндрих', 'Гордунни', None, True)
        panel = self.mpl.panel
        panel.specButton.scripts.OnClick(panel.extraLogsButton)
        actions = [entry for entry in panel.specMenu.entries.values() if entry.kind == 'button']
        self.assertTrue(actions)
        actions[-1].button.scripts.OnClick(actions[-1].button)
        pending = self.mpl.pendingReply
        self.assertTrue(pending.includeSpecs)
        self.assertEqual(pending.spec, '')
        self.assertEqual(pending.metric, 'dps')
        self.assertEqual(self.mpl.SelectedSpec('Киндрих', 'Гордунни'), 'Guardian')
        self.assertEqual(self.state(), 'pending')
        with tempfile.TemporaryDirectory(dir=specs.ROOT, prefix='.test-work-') as directory:
            reply = specs.clipboard_protocol.reply(self.mpl.downloadWindow.request,
                {'eu': {'гордунни': 'gordunni'}}, Path(directory), lambda _: self.raw(('Guardian', 'Feral')))
            self.assertEqual(self.mpl.ReceiveReply(reply, True), (1, None))
        self.assertEqual(self.state(), 'complete')
        self.assertEqual(self.mpl.panel.selectedSpec, 'Guardian')

    def test_pending_and_stale_menu_statuses_change_without_claiming_loaded_profiles(self):
        self.exchange()
        self.lua.globals().now += 24*3600
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['Refresh specialization list'])
        self.assertTrue(action.button.enabled)
        request_id, _ = self.mpl.SendRequest('Киндрих', 'Гордунни', 'dps', 'All specs', None, True)
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['Checking specializations...'])
        self.assertFalse(action.button.enabled)
        action.button.scripts.OnClick(action.button)
        self.assertEqual(self.mpl.pendingReply.id, request_id)
        self.assertIsNone(self.mpl.downloadWindow)

    def test_fresh_aggregate_available_list_suppresses_redundant_check_without_domain_marker(self):
        self.exchange(include=False)
        self.assertIsNone(self.state())
        aggregate = self.mpl.GetProfile('Киндрих', 'Гордунни', 'All specs')[0]
        self.assertEqual(list(aggregate.availableSpecs.values()), ['Guardian'])
        self.assertFalse(self.mpl.IsProfileStale(aggregate)[0])
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['No other specializations found'])
        self.assertFalse(action.button.enabled)
        self.assertIsNone(self.state())
        self.mpl.panel.viewMetric = 'hps'
        self.mpl.RenderProfileStats(self.mpl.panel)
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['Find other specializations'])
        self.assertTrue(action.button.enabled)
        self.assertIsNone(self.state('hps'))

    def test_old_reply_without_available_records_does_not_infer_completion_from_main_spec(self):
        self.mpl.companionInfo = self.lua.table_from({'capabilities': {}}, recursive=True)
        self.exchange(include=False)
        aggregate = self.mpl.GetProfile('Киндрих', 'Гордунни', 'All specs')[0]
        self.assertIsNone(aggregate.availableSpecs)
        self.assertEqual(list(self.mpl.ProfileSpecs('Киндрих', 'Гордунни').values()), ['Guardian'])
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['Find other specializations'])
        self.assertTrue(action.button.enabled)

    def test_new_fresh_aggregate_list_can_replace_stale_ui_status_without_rewriting_check(self):
        self.exchange()
        self.lua.globals().now += 24*3600
        self.assertEqual(self.state(), 'stale')
        self.exchange(include=False)
        self.assertEqual(self.state(), 'stale')
        action = self.menu_action()
        self.assertEqual(action.text, self.mpl.L['No other specializations found'])
        self.assertFalse(action.button.enabled)
        self.assertEqual(self.state(), 'stale')

    def test_targeted_alternate_spec_uses_its_own_role_and_accepts_strict_reply(self):
        key = self.mpl.Key('Киндрих', 'Гордунни')
        for current_role, spec, expected_role in (('TANK','Feral','DAMAGER'),
                                                   ('DAMAGER','Vengeance','TANK'),
                                                   ('DAMAGER','Restoration','HEALER')):
            with self.subTest(current_role=current_role, spec=spec):
                self.mpl.roles = self.lua.table_from({key: current_role})
                _, request = self.mpl.SendRequest('Киндрих','Гордунни','dps',spec,None,False)
                self.assertEqual(self.mpl.pendingReply.role,expected_role)
                raw = self.raw((spec,))
                character = raw['data']['characterData']['character']
                character['damage'] = character.pop('performance')
                character['healing'] = specs.copy.deepcopy(character['damage'])
                with tempfile.TemporaryDirectory(dir=specs.ROOT,prefix='.test-work-') as directory:
                    reply = specs.clipboard_protocol.reply(request,
                        {'eu': {'гордунни':'gordunni'}},Path(directory),lambda _:raw)
                    self.assertEqual(self.mpl.ReceiveReply(reply,True),(1,None))
                self.assertEqual(self.mpl.GetProfile('Киндрих','Гордунни',spec)[0].role,expected_role)
                self.assertIsNone(self.state())

    def test_aggregate_and_unknown_spec_requests_preserve_current_role(self):
        key = self.mpl.Key('Киндрих','Гордунни')
        self.mpl.roles = self.lua.table_from({key:'TANK'})
        for spec in ('All specs','Unknown custom spec'):
            with self.subTest(spec=spec):
                self.mpl.SendRequest('Киндрих','Гордунни','dps',spec,None,False)
                self.assertEqual(self.mpl.pendingReply.role,'TANK')


if __name__ == '__main__':
    unittest.main()
