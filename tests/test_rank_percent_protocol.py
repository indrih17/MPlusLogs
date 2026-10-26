"""WCL display metadata is optional, negotiated, and round-trips intact."""
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import test_addon
import test_name_search
import wcl_sync as wcl
import clipboard_protocol
import realm_resolver


class RankPercentProtocolTests(unittest.TestCase):
    def setUp(self):
        test_addon.AddonTests.setUp(self)
        self.lua.execute('return assert(loadstring(...))',
            (test_addon.ROOT/'Transport.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)

    def normalize(self,raw):
        return wcl.normalize(raw,SimpleNamespace(realm='Гордунни',region='eu',zone=55,
            season='test',spec=None,metric='dps',server_slug=None))

    def raw(self,dual=False,percent=97.25):
        raw=test_addon.api_fixture()
        char=raw['data']['characterData']['character']
        char['performance']['rankings'][0].update(bestSpec='Guardian',
            allStars=dict(rank=3248,rankPercent=percent,total=100000),rankPercent=99.99)
        char['performance']['allStars']=[dict(spec='Guardian',rank=48,rankPercent=99.8,points=3774)]
        if dual:
            char['damage']=char.pop('performance')
            char['healing']=copy.deepcopy(char['damage'])
        return raw

    def records(self,text):
        return [line.split('\t') for line in text.splitlines() if line.startswith('D\t')]

    def supports(self,value):
        self.mpl.companionInfo=(None if value is None else self.lua.table_from(
            dict(version='1.0.0',capabilities=dict(rankcolors=value)),recursive=True))

    def exchange(self,request,raw):
        with tempfile.TemporaryDirectory(dir=test_addon.ROOT,prefix='.test-work-') as directory:
            return clipboard_protocol.reply(request,realm_resolver.load_mappings(),Path(directory),lambda _:copy.deepcopy(raw))

    def test_captured_wcl_source_uses_allstars_percentile_not_run_or_throughput(self):
        raw=json.loads((test_addon.ROOT/'experiments/wcl-points-and-damage.json').read_text(encoding='utf-8'))
        profile=self.normalize(raw)
        source=raw['data']['characterData']['character']['performance']['rankings']
        self.assertNotEqual(source[0]['rankPercent'],source[0]['allStars']['rankPercent'])
        self.assertEqual(self.mpl.Import(wcl.export(profile,rank_colors=True)),1)
        stored=self.mpl.GetProfile('Киндрих','Гордунни')[0]
        for original,normal,received in zip(source,profile['dungeons'],stored.dungeons.values()):
            expected=original['allStars']['rankPercent']
            self.assertEqual(normal['rankPercent'],expected)
            self.assertEqual(received.rankPercent,expected)
        for original,normal,received in zip(raw['data']['characterData']['character']['performance']['allStars'],
                                           profile['specRanks'],stored.specRanks.values()):
            self.assertEqual(normal['rankPercent'],original['rankPercent'])
            self.assertEqual(received.rankPercent,original['rankPercent'])

    def test_missing_metadata_is_not_inferred_from_other_percentiles_or_rank_total(self):
        raw=self.raw()
        row=raw['data']['characterData']['character']['performance']['rankings'][0]
        del row['allStars']['rankPercent']
        profile=self.normalize(raw)
        self.assertIsNone(profile['dungeons'][0]['rankPercent'])
        self.assertEqual(self.records(wcl.export(profile,rank_colors=True)),self.records(wcl.export(profile)))
        del row['allStars']
        self.assertIsNone(self.normalize(raw)['dungeons'][0]['rankPercent'])

    def test_single_dual_scorespec_and_zero_roundtrip(self):
        for dual in (False,True):
            for details in (False,True):
                for spec in (None,'Guardian'):
                    for percent in (0,97.25,100):
                        with self.subTest(dual=dual,details=details,spec=spec,percent=percent):
                            profile=self.normalize(self.raw(dual,percent))
                            profile['dungeons'][0]['scoreSpec']=spec
                            text=wcl.export(profile,spec_details=details,rank_colors=True)
                            record=self.records(text)[0]
                            self.assertEqual(len(record),16 if dual else 12)
                            self.assertEqual(record[-2],spec if details and spec else '')
                            self.assertEqual(self.mpl.Import(text),1)
                            row=self.mpl.GetProfile('Киндрих','Гордунни')[0].dungeons[1]
                            self.assertEqual(row.rankPercent,percent)
                            self.assertEqual(row.scoreSpec,spec if details else None)

    def test_invalid_api_percentiles_are_schema_errors(self):
        for value in (-1,100.1,True,'99',float('nan'),float('inf')):
            with self.subTest(value=value):
                with self.assertRaises(wcl.ProfileError): self.normalize(self.raw(percent=value))

    def test_first_exchange_loads_complete_metadata_without_discovery_roundtrip(self):
        self.supports(None)
        _,request=self.mpl.SendRequest('Киндрих','Гордунни','dps','All specs')
        self.assertIn('rankcolors',request)
        self.assertEqual(self.mpl.ReceiveReply(self.exchange(request,self.raw(True)),True),(1,None))
        profile=self.mpl.GetProfile('Киндрих','Гордунни')[0]
        self.assertEqual(profile.displayMetadata,'complete')
        self.assertEqual(profile.dungeons[1].rankPercent,97.25)
        self.assertEqual(profile.specRanks[1].rankPercent,99.8)
        self.assertFalse(self.mpl.panel.staleBanner.shown)

    def test_captured_profile_first_exchange_renders_rank_colors_and_temple_star(self):
        raw=json.loads((test_addon.ROOT/'experiments/wcl-points-and-damage.json').read_text(encoding='utf-8'))
        self.supports(None)
        _,request=self.mpl.SendRequest('Киндрих','Гордунни','dps','All specs')
        self.assertEqual(self.mpl.ReceiveReply(self.exchange(request,raw),True),(1,None))
        profile=self.mpl.GetProfile('Киндрих','Гордунни')[0]
        panel=self.mpl.panel
        panel.profile=profile
        panel.viewMetric='dps'
        self.mpl.RenderProfileStats(panel)
        for row,dungeon in zip(panel.rows.values(),profile.dungeons.values()):
            color=self.mpl.PercentColor(dungeon.rankPercent)
            expected=[int(color[i:i+2],16)/255 for i in (0,2,4)]
            self.assertEqual(list(row.cells[6].textColor.values()),expected)
            self.assertEqual('*' in row.cells[8].text,dungeon.name=='Temple of Sethraliss')
        for entry,rank in zip(panel.specRankEntries.values(),profile.specRanks.values()):
            color=self.mpl.PercentColor(rank.rankPercent)
            expected=[int(color[i:i+2],16)/255 for i in (0,2,4)]
            self.assertEqual(list(entry.number.textColor.values()),expected)

    def test_display_metadata_is_requested_unless_known_unsupported_single_and_batch(self):
        self.assertIn('rankcolors',clipboard_protocol.CAPABILITIES)
        for batch in (False,True):
            for support in (None,False,True):
                with self.subTest(batch=batch,support=support):
                    self.supports(support)
                    if batch:
                        _,request=self.mpl.SendBatchRequest(self.lua.table_from(
                            [dict(name='Киндрих',realm='Гордунни',role='TANK')],recursive=True))
                    else:
                        _,request=self.mpl.SendRequest('Киндрих','Гордунни','dps','All specs')
                    self.assertEqual('rankcolors' in request,support is not False)
                    reply=self.exchange(request,self.raw(True))
                    payload=unquote(reply.split('MPLB1\n',1)[1])
                    self.assertEqual(len(self.records(payload)[0]),16 if support is not False else 15)
                    result=self.mpl.ReceiveReply(reply,True)
                    self.assertEqual(result[0] if isinstance(result,tuple) else result,1)
                    row=self.mpl.GetProfile('Киндрих','Гордунни')[0].dungeons[1]
                    self.assertEqual(row.rankPercent,97.25 if support is not False else None)
                    rank=self.mpl.GetProfile('Киндрих','Гордунни')[0].specRanks[1]
                    self.assertEqual(rank.rankPercent,99.8 if support is not False else None)
                    self.assertEqual(self.mpl.GetProfile('Киндрих','Гордунни')[0].displayMetadata,
                                     'complete' if support is not False else 'refresh')

    def test_old_clients_get_exact_legacy_shapes_even_with_available_metadata(self):
        for required in (None,'specdetails'):
            request=('MPLS1\n12345-1\n' if required is None else
                'MPLS2\n12345-1\nMPLC1 '+required+'\n')
            request+='MPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\t\n'
            reply=self.exchange(request,self.raw(True))
            payload=unquote(reply.split('MPLB1\n',1)[1])
            self.assertEqual(len(self.records(payload)[0]),14 if required is None else 15)
            self.assertEqual(self.mpl.Import(payload),1)
            self.assertIsNone(self.mpl.GetProfile('Киндрих','Гордунни')[0].dungeons[1].rankPercent)

    def test_older_helper_loads_logs_and_marks_missing_display_metadata(self):
        self.supports(False)
        self.assertEqual(self.mpl.Import(wcl.export(self.normalize(self.raw(True)),rank_colors=True)),1)
        _,request=self.mpl.SendRequest('Киндрих','Гордунни','dps','All specs')
        with patch.object(clipboard_protocol,'CAPABILITIES',clipboard_protocol.CAPABILITIES-{'rankcolors'}):
            reply=self.exchange(request,self.raw(True))
        self.assertEqual(self.mpl.ReceiveReply(reply,True),(1,None))
        profile=self.mpl.GetProfile('Киндрих','Гордунни')[0]
        self.assertIsNone(profile.dungeons[1].rankPercent)
        self.assertIsNone(profile.specRanks[1].rankPercent)
        self.assertEqual(profile.displayMetadata,'companion')
        self.assertIn(self.mpl.L['Некоторые данные отсутствуют. Обновите MPlusLogs Companion.'],self.mpl.panel.staleBanner.message.text)

    def test_mixed_old_and_extended_rows_preserve_unknowns_and_dungeon_limit(self):
        profile=self.normalize(self.raw())
        unknown=copy.deepcopy(profile['dungeons'][0])
        unknown.update(name='Unknown',rankPercent=None)
        profile['dungeons'].append(unknown)
        text=wcl.export(profile,rank_colors=True)
        self.assertEqual([len(row) for row in self.records(text)],[12,11])
        self.assertEqual(self.mpl.Import(text),1)
        rows=self.mpl.GetProfile('Киндрих','Гордунни')[0].dungeons
        self.assertEqual(rows[1].rankPercent,97.25)
        self.assertIsNone(rows[2].rankPercent)
        profile['dungeons']=[copy.deepcopy(profile['dungeons'][0]) for _ in range(32)]
        self.assertEqual(self.mpl.Import(wcl.export(profile,rank_colors=True)),1)
        profile['dungeons'].append(unknown)
        count,error=self.mpl.Import(wcl.export(profile,rank_colors=True))
        self.assertIsNone(count); self.assertTrue(error)

    def test_wire_percentiles_and_shape_limits_are_validated(self):
        for dual in (False,True):
            profile=self.normalize(self.raw(dual))
            text=wcl.export(profile,rank_colors=True)
            original=next(line for line in text.splitlines() if line.startswith('D\t'))
            fields=original.split('\t')
            for value in ('','-1','100.1','nan','inf','false'):
                with self.subTest(dual=dual,value=value):
                    malformed='\t'.join(fields[:-1]+[value])
                    count,error=self.mpl.Import(text.replace(original,malformed))
                    self.assertIsNone(count); self.assertTrue(error)
            for malformed in ('\t'.join(fields+['extra']), '\t'.join(fields[:-2])):
                if malformed=='\t'.join(fields[:-2]):
                    # Old base row is valid; a blank legacy scoreSpec is not.
                    malformed+='\t'
                count,error=self.mpl.Import(text.replace(original,malformed))
                self.assertIsNone(count); self.assertTrue(error)
            if not dual:
                count,error=self.mpl.Import(text.replace(original,'\t'.join(fields+['','','',''])))
                self.assertIsNone(count); self.assertTrue(error)

    def test_secondary_pending_keeps_complete_empty_secondary_fields(self):
        profile=self.normalize(self.raw(True))
        profile.update(secondaryPending=True,role='DAMAGER',otherBest=None,otherMedian=None)
        for key in ('otherLevel','otherAmount','otherBest','otherMedian'):
            profile['dungeons'][0][key]=None
        text=wcl.export(profile,rank_colors=True)
        self.assertEqual(self.mpl.Import(text),1)
        original=next(line for line in text.splitlines() if line.startswith('D\t'))
        fields=original.split('\t'); fields[11]='1'
        count,error=self.mpl.Import(text.replace(original,'\t'.join(fields)))
        self.assertIsNone(count); self.assertTrue(error)

    def test_shared_percent_palette_preserves_existing_output(self):
        self.assertIsNone(self.mpl.PercentColor(None))
        self.assertEqual(self.mpl.Percent(None),'—')
        for value,color in ((0,'666666'),(25,'1eff00'),(50,'0070ff'),(75,'a335ee'),
                            (95,'ff8000'),(99,'e268a8'),(100,'e5cc80')):
            self.assertEqual(self.mpl.PercentColor(value),color)
            self.assertEqual(self.mpl.Percent(value),'|cff'+color+str(value)+'%|r')
            self.assertEqual(self.mpl.Percent(value,True),'|cff'+color+str(value)+'%|r')

    def test_spec_rank_colors_only_export_when_negotiated_and_details_enabled(self):
        raw=self.raw()
        raw['data']['characterData']['character']['performance']['allStars']=[
            dict(spec='Guardian',rank=48,rankPercent=99.8)]
        profile=self.normalize(raw)
        for colors in (False,True):
            for details in (False,True):
                with self.subTest(colors=colors,details=details):
                    text=wcl.export(profile,rank_colors=colors,spec_details=details)
                    records=[line for line in text.splitlines() if line.startswith('R\t')]
                    self.assertEqual(records,['R\tGuardian\t48'+('\t99.8' if colors else '')] if details else [])
                    self.assertEqual(self.mpl.Import(text),1)
                    stored=self.mpl.GetProfile('Киндрих','Гордунни')[0]
                    if details: self.assertEqual(stored.specRanks[1].rankPercent,99.8 if colors else None)
                    else: self.assertIsNone(stored.specRanks)

    def test_spec_percentile_ambiguity_omits_color_and_keeps_matching_rank(self):
        for percents in ((99,99),(0,0),(99,95),(99,None),(None,99),(99,95,99)):
            with self.subTest(percents=percents):
                raw=self.raw()
                raw['data']['characterData']['character']['performance']['allStars']=[
                    dict(spec='Guardian',rank=48,rankPercent=percent) for percent in percents]
                expected=percents[0] if len(set(percents))==1 else None
                profile=self.normalize(raw)
                self.assertEqual(profile['specRanks'][0]['rank'],48)
                self.assertEqual(profile['specRanks'][0].get('rankPercent'),expected)
                base=wcl.export(profile,spec_details=False)
                records=''.join('R\tGuardian\t48'+('' if percent is None else '\t'+str(percent))+'\n'
                                for percent in percents)
                self.assertEqual(self.mpl.Import(base.replace('E\n',records+'E\n')),1)
                rank=self.mpl.GetProfile('Киндрих','Гордунни')[0].specRanks[1]
                self.assertEqual(rank.rank,48)
                self.assertEqual(rank.rankPercent,expected)

    def test_spec_rank_extension_rejects_bad_values_and_shapes(self):
        text=wcl.export(self.normalize(self.raw()),spec_details=False)
        for record in ('R\tGuardian\t48\t','R\tGuardian\t48\t-1','R\tGuardian\t48\t101',
                       'R\tGuardian\t48\tnan','R\tGuardian\t48\tinf','R\tGuardian\t48\t99\textra',
                       'R\tGuardian\t0\t99','R\tGuardian\t1.5\t99'):
            with self.subTest(record=record):
                count,error=self.mpl.Import(text.replace('E\n',record+'\nE\n'))
                self.assertIsNone(count); self.assertTrue(error)
        for value in (-1,101,'99',True,float('nan')):
            raw=self.raw()
            raw['data']['characterData']['character']['performance']['allStars']=[
                dict(spec='Guardian',rank=48,rankPercent=value)]
            with self.assertRaises(wcl.ProfileError): self.normalize(raw)
        count,error=self.mpl.Import(text.replace('E\n','R\tGuardian\t48\t99\n'*65+'E\n'))
        self.assertIsNone(count); self.assertTrue(error)

    def test_spec_rank_extension_preserves_conflicting_rank_omission(self):
        raw=self.raw()
        raw['data']['characterData']['character']['performance']['allStars']=[
            dict(spec='Guardian',rank=rank,rankPercent=99) for rank in (48,207,48)]
        profile=self.normalize(raw)
        self.assertEqual(profile['specRanks'],[])
        text=wcl.export(profile)
        self.assertEqual(self.mpl.Import(text.replace('E\n',
            'R\tGuardian\t48\t99\nR\tGuardian\t207\t99\nR\tGuardian\t48\t99\nE\n')),1)
        self.assertEqual(len(self.mpl.GetProfile('Киндрих','Гордунни')[0].specRanks),0)


class RankPercentNameSearchTests(unittest.TestCase):
    setUp=test_name_search.NameSearchTests.setUp

    def test_search_profile_metadata_on_first_exchange_unless_known_unsupported(self):
        class Client(test_name_search.Client):
            def __call__(self,args):
                raw=super().__call__(args)
                for metric in ('damage','healing'):
                    raw['data']['characterData']['character'][metric]['rankings'][0]['allStars']={
                        'rank':3248,'rankPercent':96.75}
                    raw['data']['characterData']['character'][metric]['allStars']=[
                        dict(spec='Arms',rank=1268,rankPercent=96.25,points=3774)]
                return raw
        for support in (None,False,True):
            with self.subTest(support=support):
                self.mpl.companionInfo=(None if support is None else self.lua.table_from(
                    dict(version='1.0.0',capabilities=dict(rankcolors=support)),recursive=True))
                self.mpl.BeginSearchGroupRequest()
                request=self.mpl.searchGroupWindow.request
                self.assertEqual('rankcolors' in request,support is not False)
                reply=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,Client())
                self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
                for player in self.mpl.searchGroupWindow.players.values():
                    profile=self.mpl.GetProfile(player.name,player.realm)[0]
                    self.assertEqual(profile.dungeons[1].rankPercent,96.75 if support is not False else None)
                    self.assertEqual(profile.specRanks[1].rankPercent,96.25 if support is not False else None)


if __name__=='__main__':
    unittest.main()
