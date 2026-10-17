"""Per-result specialization and WCL spec ranks survive the full data path."""
import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.parse import quote, unquote
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

    def test_duplicate_wcl_spec_ranks_do_not_block_profile_import(self):
        raw=self.raw()
        for metric in ('damage','healing'):
            raw['data']['characterData']['character'][metric]['allStars']=[
                {'spec':'Holy','rank':3637,'partition':1},
                {'spec':'Holy','rank':4239,'partition':1},
                {'spec':'Outlaw','rank':1221},
                {'spec':'Outlaw','rank':1221}]
        profile=self.normalize(raw)
        self.assertEqual(profile['specRanks'],[{'spec':'Outlaw','rank':1221}])
        self.assertEqual(self.mpl.Import(wcl.export(profile)),1)
        self.assertEqual(len(self.mpl.GetProfile('Киндрих','Гордунни')[0].dungeons),2)

    def test_old_companion_duplicate_rank_rows_preserve_logs_and_omit_conflicts(self):
        text=wcl.export(self.normalize(self.raw()),spec_details=False)
        text=text.replace('E\n','R\tHoly\t3637\nR\tHoly\t4239\nR\tHoly\t3637\n'
                          'R\tOutlaw\t1221\nR\tOutlaw\t1221\nE\n')
        self.assertEqual(self.mpl.Import(text),1)
        profile=self.mpl.GetProfile('Киндрих','Гордунни')[0]
        self.assertEqual(len(profile.dungeons),2)
        self.assertEqual(len(profile.specRanks),1)
        self.assertEqual(profile.specRanks[1].spec,'Outlaw')
        self.assertEqual(profile.specRanks[1].rank,1221)

    def rank_reply_contract(self, legacy_rows=False):
        # Exercise both sides of the real clipboard boundary, including a
        # healthy neighbour in a batch. No network or personal cache is used.
        patterns = [[], [3637], [3637,3637], [3637,4239],
                    [3637,4239,3637], [4239,3637,4239]]
        for ranks in patterns:
            for batch in (False,True):
                for role in ('DAMAGER','HEALER'):
                    with self.subTest(ranks=ranks,batch=batch,role=role,legacy=legacy_rows):
                        self.setUp()
                        self.lua.execute('return assert(loadstring(...))',
                            (test_addon.ROOT/'Transport.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
                        if batch:
                            players=self.lua.table_from([
                                dict(name=name,realm='Гордунни',role=role)
                                for name in ('Affected','Unaffected')],recursive=True)
                            _,request=self.mpl.SendBatchRequest(players)
                        else:
                            _,request=self.mpl.SendRequest('Affected','Гордунни',
                                'hps' if role=='HEALER' else 'dps','All specs')
                        def fetch(args):
                            raw=self.raw()
                            char=raw['data']['characterData']['character']
                            char['name']=args.name
                            for metric in ('damage','healing'):
                                char[metric]['allStars']=[
                                    {'spec':'Holy','rank':rank,'partition':1}
                                    for rank in (ranks if args.name=='Affected' and not legacy_rows else [1221])]
                            return raw
                        with tempfile.TemporaryDirectory(dir=test_addon.ROOT,prefix='.test-work-') as directory:
                            reply=clipboard_protocol.reply(request,realm_resolver.load_mappings(),Path(directory),fetch)
                        if legacy_rows:
                            head,body=reply.split('MPLB1\n',1)
                            # An old Companion forwarded allStars rows unchanged.
                            body=unquote(body).replace('R\tHoly\t1221\n',
                                ''.join('R\tHoly\t'+str(rank)+'\n' for rank in ranks),1)
                            reply=head+'MPLB1\n'+quote(body,safe='')
                        result=self.mpl.ReceiveReply(reply,True)
                        count=result[0] if isinstance(result,tuple) else result
                        self.assertEqual(count,2 if batch else 1,msg=str(result))
                        self.assertIsNone(self.mpl.pendingReply)
                        for name in ('Affected','Unaffected') if batch else ('Affected',):
                            profile=self.mpl.GetProfile(name,'Гордунни')[0]
                            self.assertEqual(len(profile.dungeons),2)
                            self.assertEqual(profile.dungeons[1].amount,168110)
                            self.assertEqual(profile.metric,'hps' if role=='HEALER' else 'dps')
                            expected=[dict(spec='Holy',rank=1221)]
                            if name=='Affected':
                                expected=([dict(spec='Holy',rank=ranks[0])]
                                    if ranks and len(set(ranks))==1 else [])
                            actual=([dict(spec=row.spec,rank=row.rank) for row in profile.specRanks.values()]
                                if profile.specRanks is not None else [])
                            self.assertEqual(actual,expected)

    def test_wcl_rank_variations_survive_single_and_group_clipboard_exchange(self):
        self.rank_reply_contract()

    def test_legacy_rank_variations_survive_single_and_group_clipboard_exchange(self):
        self.rank_reply_contract(legacy_rows=True)

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
        for record in ['R\tOutlaw\t0\n','R\tOutlaw\t1.5\n','R\tOutlaw\t1\n'*65]:
            count,error=self.mpl.Import(text.replace('E\n',record+'E\n'))
            self.assertIsNone(count)
            self.assertTrue(error)


if __name__ == '__main__':
    unittest.main()
