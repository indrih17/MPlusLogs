"""Role evidence must resolve identities without equating missing logs with mismatch."""
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote
import test_name_search
import name_search


class RoleClient(test_name_search.Client):
    def __init__(self, specs=('Protection', 'Arms'), empty=()):
        super().__init__(realms=('draenor', 'silvermoon'))
        self.specs=specs
        self.empty=empty

    def __call__(self,args):
        raw=super().__call__(args)
        char=raw['data']['characterData']['character']
        spec=self.specs[0 if args.server_slug=='draenor' else 1]
        for field in ('damage','healing'):
            data=char[field]
            if spec:
                data['rankings'][0]['bestSpec']=spec
                data['allStars']=[dict(spec=spec,points=2500)]
            if args.server_slug in self.empty:
                data['throughputRankings']={}
        return raw


class NameSearchRoleTests(unittest.TestCase):
    def response(self,client,role='DAMAGER',realm='',class_name='WARRIOR',name='Mirkowrr',key_range=None,**options):
        with tempfile.TemporaryDirectory(dir=test_name_search.test_addon.ROOT) as folder:
            body='MPLN1\nN\t1\teu\t'+realm+'\t'+name+'\t'+class_name+'\t'+role+'\tsearch\n'
            if key_range: body=body.rstrip('\n')+'\t90\t'+str(key_range[0])+'\t'+str(key_range[1])+'\n'
            return name_search.reply(body,{'eu':{'silvermoon':'silvermoon'}},Path(folder),client,**options)

    def test_only_damage_candidate_is_selected_for_damage_slot(self):
        result=self.response(RoleClient())
        self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\tSilvermoon\t'),result)

    def test_only_tank_candidate_is_selected_for_tank_slot(self):
        result=self.response(RoleClient(),role='TANK')
        self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\tDraenor\t'),result)

    def test_unknown_role_evidence_keeps_choice(self):
        result=self.response(RoleClient(specs=(None,'Arms')))
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

    def test_missing_throughput_does_not_remove_identity(self):
        result=self.response(RoleClient(specs=('Arms','Arms'),empty=('draenor',)))
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

    def test_choices_supply_rating_specs_and_logs_only_when_negotiated(self):
        for extended in (False,True):
            result=self.response(RoleClient(specs=('Arms','Arms')),candidate_info=extended)
            rows=[[unquote(f) for f in r.split('\t')] for r in result.splitlines()[1:]]
            self.assertEqual([len(r) for r in rows],[12 if extended else 6]*2)
            if extended:
                self.assertEqual(rows[0][6:9],['','','472'])
                self.assertEqual(rows[0][9:12],['62','27','Arms'])

    def test_same_role_on_both_realms_remains_a_choice(self):
        result=self.response(RoleClient(specs=('Arms','Fury')))
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

    def test_rating_alone_can_resolve_but_missing_logs_still_returns_no_logs(self):
        result=self.response(RoleClient(empty=('draenor',)),role='TANK',error_details=True)
        row=result.splitlines()[1].split('\t')
        self.assertEqual(row[:6],['F','1','eu','Draenor','Mirkowrr','WARRIOR'])

    def test_duplicate_metrics_do_not_double_role_score(self):
        args=type('Args',(),dict(name='Mirkowrr',server_slug='draenor'))()
        raw=RoleClient()(args)
        evidence=name_search.candidate_evidence(raw,'WARRIOR')
        self.assertEqual(evidence['scores'],{'TANK':472})
        self.assertEqual(evidence['roles'],{'TANK'})

    def test_invalid_spec_does_not_become_damage_evidence(self):
        args=type('Args',(),dict(name='Mirkowrr',server_slug='draenor'))()
        raw=RoleClient(specs=('UnknownFutureSpec','Arms'))(args)
        self.assertEqual(name_search.candidate_evidence(raw,'WARRIOR')['roles'],set())

    def test_alternative_spec_rank_does_not_override_dungeon_points(self):
        class Hybrid(RoleClient):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.server_slug=='draenor':
                    raw['data']['characterData']['character']['damage']['allStars'].append(
                        dict(spec='Arms',points=1800))
                return raw
        result=self.response(Hybrid())
        self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\tSilvermoon\t'),result)

    def shaman_client(self, points, levels=None):
        class Shamans(test_name_search.Client):
            def __init__(self):
                super().__init__(realms=('silvermoon','tarren-mill'))

            def __call__(self,args):
                raw=super().__call__(args)
                char=raw['data']['characterData']['character']
                raw['data']['gameData']['classes'].append({'id':80,'name':'Shaman'})
                char['classID']=80
                damage,healing=points[args.server_slug]
                for field in ('damage','healing'):
                    data=char[field]
                    template=dict(data['rankings'][0])
                    data['rankings']=[dict(template,encounter=dict(template['encounter'],id=i+1),bestSpec=spec,
                                           bestAmount=score,totalKills=1)
                                      for i,(spec,score) in enumerate((('Elemental',damage),('Restoration',healing)))]
                    # Both characters have ranks in both specs, even with zero points.
                    data['allStars']=[dict(spec=spec,points=4000)
                                      for spec in ('Elemental','Restoration')]
                    if levels is not None:
                        level=levels[args.server_slug]
                        for row in data['rankings']:
                            row['bestRank']={'ilvl':level}
                        for run in data['throughputRankings'].values():
                            run['best_level']=level
                return raw
        return Shamans()

    def test_stormek_healer_uses_majority_of_points(self):
        client=self.shaman_client({'silvermoon':(3651,0),'tarren-mill':(1457,2425)})
        result=self.response(client,role='HEALER',class_name='SHAMAN',name='Stormek')
        self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\tTarren-Mill\tStormek\t'),result)

    def test_stormek_damage_uses_majority_of_points(self):
        client=self.shaman_client({'silvermoon':(3651,0),'tarren-mill':(1457,2425)})
        result=self.response(client,class_name='SHAMAN',name='Stormek')
        self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\tSilvermoon\tStormek\t'),result)

    def test_tied_or_missing_points_keep_realm_choice(self):
        for other in ((1000,1000),(0,0)):
            with self.subTest(other=other):
                client=self.shaman_client({'silvermoon':other,'tarren-mill':(500,3000)})
                result=self.response(client,role='HEALER',class_name='SHAMAN',name='Stormek')
                self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

    def test_two_healer_majorities_keep_realm_choice(self):
        client=self.shaman_client({'silvermoon':(100,2000),'tarren-mill':(500,3000)})
        result=self.response(client,role='HEALER',class_name='SHAMAN',name='Stormek')
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

    def test_listing_level_takes_priority_over_role_points(self):
        for key_range,realm in (((18,18),'Silvermoon'),((19,19),'Silvermoon'),
                                ((18,19),'Silvermoon'),((20,20),'Tarren-Mill'),
                                ((21,21),'Tarren-Mill'),((20,21),'Tarren-Mill')):
            with self.subTest(key_range=key_range):
                client=self.shaman_client({'silvermoon':(3651,0),'tarren-mill':(1457,2425)},
                                          {'silvermoon':18,'tarren-mill':21})
                result=self.response(client,role='HEALER',class_name='SHAMAN',name='Stormek',key_range=key_range)
                self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\t'+realm+'\tStormek\t'),result)

    def test_equal_key_distance_uses_role_majority(self):
        client=self.shaman_client({'silvermoon':(3651,0),'tarren-mill':(1457,2425)},
                                  {'silvermoon':18,'tarren-mill':20})
        result=self.response(client,role='HEALER',class_name='SHAMAN',name='Stormek',key_range=(19,19))
        self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\tTarren-Mill\t'),result)

    def test_missing_key_level_does_not_exclude_a_candidate(self):
        client=self.shaman_client({'silvermoon':(100,2000),'tarren-mill':(100,3000)},
                                  {'silvermoon':18,'tarren-mill':None})
        result=self.response(client,role='HEALER',class_name='SHAMAN',name='Stormek',key_range=(18,18))
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

    def empty_season_client(self,empty=('draenor',)):
        class EmptySeason(RoleClient):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.server_slug in empty:
                    char=raw['data']['characterData']['character']
                    for field in ('damage','healing'):
                        char[field]['rankings']=[]
                        char[field]['allStars']=[]
                        char[field]['throughputRankings']={}
                return raw
        return EmptySeason(specs=('Arms','Arms'))

    def test_empty_season_is_excluded_only_above_ten(self):
        for key_range in (None,(10,10),(10,11),(11,11),(18,19)):
            with self.subTest(key_range=key_range):
                result=self.response(self.empty_season_client(),key_range=key_range)
                kinds=[r.split('\t')[0] for r in result.splitlines()[1:]]
                self.assertEqual(kinds,['P'] if key_range and key_range[0]>10 else ['C','C'])
                if kinds==['P']: self.assertIn('\tSilvermoon\t',result)

    def test_empty_high_key_search_never_falls_back_to_empty_identity(self):
        result=self.response(self.empty_season_client(empty=('draenor','silvermoon')),key_range=(11,11))
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['F'])

    def test_known_empty_realm_still_returns_no_logs(self):
        result=self.response(self.empty_season_client(empty=('silvermoon',)),realm='silvermoon',key_range=(11,11),error_details=True)
        self.assertTrue(result.splitlines()[1].startswith('F\t1\teu\tSilvermoon\t'),result)

    def test_high_key_search_preserves_leaderboard_without_uploads(self):
        class Leaderboard(RoleClient):
            def __call__(self,args):
                raw=super().__call__(args)
                for field in ('damage','healing'):
                    data=raw['data']['characterData']['character'][field]
                    for row in data['rankings']: row['bestRank']={'ilvl':18}
                    for run in data['throughputRankings'].values(): run['best_level']=18
                return raw
        result=self.response(Leaderboard(specs=('Arms','Arms'),empty=('draenor',)),key_range=(18,18))
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

    def test_hidden_candidate_blocks_high_key_autoselection(self):
        class Hidden(RoleClient):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.server_slug=='draenor': raw['data']['characterData']['character']['hidden']=True
                return raw
        result=self.response(Hidden(),key_range=(18,18),error_codes=True)
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['F'])
        self.assertIn('hidden',unquote(result))

    def test_known_realm_overrides_key_and_role(self):
        client=self.shaman_client({'silvermoon':(3651,0),'tarren-mill':(1457,2425)},
                                  {'silvermoon':18,'tarren-mill':21})
        result=self.response(client,role='HEALER',realm='silvermoon',class_name='SHAMAN',name='Stormek',key_range=(21,21))
        self.assertTrue(result.splitlines()[1].startswith('P\t1\teu\tSilvermoon\t'),result)

    def test_key_context_parser_validates_separate_character_and_key_levels(self):
        prefix='MPLN1\nN\t1\teu\t\tStormek\tSHAMAN\tHEALER\tsearch'
        member=name_search.parse(prefix+'\t90\t18\t19\n')[0]
        self.assertEqual((member['min_level'],member['key_min'],member['key_max']),(90,18,19))
        self.assertIsNone(name_search.parse(prefix+'\t\t18\t18\n')[0]['min_level'])
        for suffix in ('\t90\t19\t18','\t90\t0\t18','\t90\t18\t101','\t90\t18.5\t19','\t90\t18'):
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):
                name_search.parse(prefix+suffix+'\n')

    def test_zero_scores_and_zero_runs_do_not_prove_a_role(self):
        args=type('Args',(),dict(name='Mirkowrr',server_slug='draenor'))()
        raw=RoleClient()(args)
        for field in ('damage','healing'):
            data=raw['data']['characterData']['character'][field]
            data['allStars'][0]['points']=0
            data['rankings'][0].update(bestAmount=0,totalKills=0)
        evidence=name_search.candidate_evidence(raw,'WARRIOR')
        self.assertEqual(evidence['roles'],set())
        self.assertEqual(evidence['scores'],{})


if __name__=='__main__': unittest.main()
