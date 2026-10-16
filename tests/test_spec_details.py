"""Per-result specialization and WCL spec ranks survive the full data path."""
import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.parse import unquote
import test_addon
import sys
sys.path.insert(0, str(test_addon.ROOT / 'tools'))
import wcl_sync as wcl
import clipboard_protocol
import realm_resolver


class SpecDetailsTests(unittest.TestCase):
    setUp = test_addon.AddonTests.setUp

    def raw(self):
        raw = test_addon.api_fixture()
        char = raw['data']['characterData']['character']
        char['damage'] = char.pop('performance')
        damage = char['damage']
        damage['allStars'] = [{'spec':'Assassination','rank':40,'points':3000},
                              {'spec':'Outlaw','rank':1221,'points':2000}]
        damage['rankings'][0].update(bestSpec='Outlaw', spec='Assassination', totalKills=1)
        second = copy.deepcopy(damage['rankings'][0])
        second.update(encounter={'id':12813,'name':'Murder Row'}, bestSpec='Assassination', totalKills=20)
        damage['rankings'].append(second)
        damage['throughputRankings']['12813'] = copy.deepcopy(damage['throughputRankings']['12825'])
        char['healing'] = copy.deepcopy(damage)
        return raw

    def normalize(self, raw):
        return wcl.normalize(raw, SimpleNamespace(realm='Гордунни', region='eu', zone=55,
                             season='test', spec=None, metric='dps', server_slug=None))

    def icons(self):
        self.lua.execute('''UnitClass=function() return "Rogue","ROGUE" end
        GetSpecializationInfoByID=function(id)
            return id,"Spec "..id,nil,id*10
        end''')

    def test_companion_to_ui_uses_result_spec_and_wcl_rank(self):
        self.icons()
        self.lua.execute('return assert(loadstring(...))',
                         (test_addon.ROOT/'Transport.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        _, request = self.mpl.SendRequest('Киндрих','Гордунни','dps','All specs')
        with tempfile.TemporaryDirectory(dir=test_addon.ROOT,prefix='.test-work-') as directory:
            reply = clipboard_protocol.reply(request,realm_resolver.load_mappings(),Path(directory),lambda _:self.raw())
        self.assertEqual(self.mpl.ReceiveReply(reply,True),(1,None))
        panel = self.mpl.panel
        self.assertEqual(panel.profile.primarySpec,'Assassination')
        self.assertEqual(panel.rows[1].scoreSpecIcon.spec,'Outlaw')
        self.assertEqual(panel.rows[2].scoreSpecIcon.spec,'Assassination')
        self.assertTrue(panel.rows[1].scoreSpecIcon.shown)
        self.assertEqual(panel.rows[1].cells[5].text,'472')
        self.assertEqual(panel.specRanks.text,'Spec Ranks:  40 |T2590:18:18|t    1221 |T2600:18:18|t')
        self.assertTrue(panel.specRanks.shown)
        panel.rows[1].scoreSpecIcon.scripts.OnEnter(panel.rows[1].scoreSpecIcon)
        self.assertEqual(self.lua.globals().GameTooltip.lines[1][1],'Spec 260')
        panel.metricTabs.hps.scripts.OnClick()
        self.assertFalse(panel.rows[1].scoreSpecIcon.shown)
        panel.metricTabs.dps.scripts.OnClick()
        self.assertTrue(panel.rows[1].scoreSpecIcon.shown)
        self.mpl.ShowProfile('Nobody','Гордунни')
        self.assertFalse(panel.specRanks.shown)

    def test_legacy_export_and_missing_result_spec(self):
        profile = self.normalize(self.raw())
        legacy = wcl.export(profile,spec_details=False)
        self.assertNotIn('\nR\t',legacy)
        self.assertEqual(len(next(line for line in legacy.splitlines() if line.startswith('D\t')).split('\t')),14)
        self.assertEqual(self.mpl.Import(legacy),1)
        self.icons()
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.assertFalse(self.mpl.panel.rows[1].scoreSpecIcon.shown)
        self.assertFalse(self.mpl.panel.specRanks.shown)
        self.mpl.Import(wcl.export(profile))
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.assertTrue(self.mpl.panel.rows[1].scoreSpecIcon.shown)
        raw = self.raw()
        del raw['data']['characterData']['character']['damage']['rankings'][0]['bestSpec']
        profile = self.normalize(raw)
        self.assertIsNone(profile['dungeons'][0]['scoreSpec'])

    def test_old_addon_receives_only_legacy_records(self):
        request='MPLS1\n12345-1\nMPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\t\n'
        with tempfile.TemporaryDirectory(dir=test_addon.ROOT,prefix='.test-work-') as directory:
            reply=clipboard_protocol.reply(request,realm_resolver.load_mappings(),Path(directory),lambda _:self.raw())
        body=unquote(reply.split('MPLB1\n',1)[1])
        self.assertNotIn('\nR\t',body)
        self.assertEqual(len(next(line for line in body.splitlines() if line.startswith('D\t')).split('\t')),14)

    def test_single_metric_roundtrip_and_invalid_rank_records(self):
        raw=self.raw(); char=raw['data']['characterData']['character']
        char['performance']=char.pop('damage'); del char['healing']
        text=wcl.export(self.normalize(raw))
        self.assertEqual(self.mpl.Import(text),1)
        profile=self.mpl.GetProfile('Киндрих','Гордунни')[0]
        self.assertEqual(profile.dungeons[1].scoreSpec,'Outlaw')
        for record in ['R\tOutlaw\t0\n','R\tOutlaw\t1.5\n','R\tOutlaw\t1\nR\tOutlaw\t2\n']:
            count,error=self.mpl.Import(text.replace('E\n',record+'E\n'))
            self.assertIsNone(count)
            self.assertTrue(error)


if __name__ == '__main__':
    unittest.main()
