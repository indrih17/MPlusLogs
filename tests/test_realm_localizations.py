"""Exhaustive local checks against the public WCL catalogue captured 2026-10-18."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import name_search
import realm_resolver


class RealmLocalizationTests(unittest.TestCase):
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
