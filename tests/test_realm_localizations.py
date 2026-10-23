"""Exhaustive local checks against the public WCL catalogue captured 2026-10-18."""
import json
from pathlib import Path
import sys
import unittest
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import name_search
import realm_resolver


class RealmLocalizationTests(unittest.TestCase):
    def test_chogall_game_request_resolves_in_both_regions(self):
        mapping=realm_resolver.load_mappings()
        for region in ('eu','us'):
            for mark in ("'", '\u2018', '\u2019', '\u02bc', '\uff07', ''):
                with self.subTest(region=region,mark=mark):
                    entry=realm_resolver.parse_queue(
                        f'MPLQ2\nQ\t{region}\tCho{mark}gall\tMignon\tdps\t259\tDAMAGER',mapping)[0]
                    self.assertEqual(entry['server_slug'],'chogall')
                    self.assertEqual(entry['realm'],f'Cho{mark}gall')

    def test_all_bundled_realms_accept_equivalent_typography(self):
        mapping=realm_resolver.load_mappings()
        for region,names in mapping.items():
            for name,slug in names.items():
                variants={unicodedata.normalize('NFD',name),name.upper()}
                for mark in ("'", '\u2018', '\u2019', '\u02bc', '\uff07', ''):
                    variants.add(name.replace("'",mark).replace('\u2019',mark))
                for space in ('', '\u00a0', '\u202f'):
                    variants.add(name.replace(' ',space))
                for dash in ('', '\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2212', '\ufe63', '\uff0d'):
                    variants.add(name.replace('-',dash))
                for variant in variants:
                    with self.subTest(region=region,realm=name,variant=variant):
                        self.assertEqual(realm_resolver.resolve(mapping,region,variant),slug)

    def test_normalization_preserves_identity_and_rejects_ambiguity(self):
        mapping={'eu':{"A'b":'first','A\u2019b':'second','Caf\u00e9':'accented'},
                 'us':{"A'b":'american'}}
        self.assertEqual(realm_resolver.resolve(mapping,'eu',"A'b"),'first')
        self.assertEqual(realm_resolver.resolve(mapping,'us',"A'b"),'american')
        for region,realm in (('eu','Ab'),('eu','A\u2018b'),('eu','Cafe'),('eu','A.b'),('kr',"A'b")):
            with self.subTest(region=region,realm=realm):
                with self.assertRaisesRegex(ValueError,'Unknown/ambiguous realm'):
                    realm_resolver.resolve(mapping,region,realm)

    def test_every_official_realm_name_resolves_to_its_canonical_slug(self):
        catalogue=json.loads((ROOT/'packaging/realm-catalogue-audit.json').read_text(encoding='utf-8'))['regions']
        mapping=realm_resolver.load_mappings()
        for region,servers in catalogue.items():
            for server in servers:
                for label in {server['name'],server['normalizedName']}:
                    if not label: continue  # WCL omits seven CN normalized labels.
                    with self.subTest(region=region,realm=label):
                        self.assertEqual(realm_resolver.resolve(mapping,region,label),server['slug'])

    def test_every_official_realm_is_verified_by_id_without_spelling_comparison(self):
        catalogue=json.loads((ROOT/'packaging/realm-catalogue-audit.json').read_text(encoding='utf-8'))['regions']
        for region,servers in catalogue.items():
            for server in servers:
                raw={'data':{'gameData':{'classes':[{'id':11,'name':'Warrior'}]},
                    'worldData':{'server':{'id':server['id']}},
                    'characterData':{'character':{'name':'Test','classID':11,'server':server}}}}
                with self.subTest(region=region,realm=server['name']):
                    self.assertIsNotNone(name_search.verified(raw,dict(name='Test',region=region,class_name='WARRIOR'),server['normalizedName']))
                    raw['data']['worldData']['server']['id']=-1
                    with self.assertRaises(ValueError):
                        name_search.verified(raw,dict(name='Test',region=region,class_name='WARRIOR'),server['slug'])


if __name__=='__main__': unittest.main()
