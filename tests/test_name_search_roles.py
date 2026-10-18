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
    def response(self,client,role='DAMAGER',realm='',**options):
        with tempfile.TemporaryDirectory(dir=test_name_search.test_addon.ROOT) as folder:
            body='MPLN1\nN\t1\teu\t'+realm+'\tMirkowrr\tWARRIOR\t'+role+'\tsearch\n'
            return name_search.reply(body,{'eu':{}},Path(folder),client,**options)

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

    def test_alternative_spec_evidence_preserves_real_ambiguity(self):
        class Hybrid(RoleClient):
            def __call__(self,args):
                raw=super().__call__(args)
                if args.server_slug=='draenor':
                    raw['data']['characterData']['character']['damage']['allStars'].append(
                        dict(spec='Arms',points=1800))
                return raw
        result=self.response(Hybrid())
        self.assertEqual([r.split('\t')[0] for r in result.splitlines()[1:]],['C','C'])

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
