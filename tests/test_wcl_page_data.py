"""WCL score metadata survives normalization, export, import, and display."""
import copy
import json
from types import SimpleNamespace
import unittest

import test_addon

wcl = test_addon.sync


class WCLPageDataTests(unittest.TestCase):
    setUp = test_addon.AddonTests.setUp

    def args(self, spec=None):
        return SimpleNamespace(realm='Гордунни', region='eu', zone=55,
                               season='test', spec=spec, metric='dps', server_slug=None)

    def raw(self):
        raw = test_addon.api_fixture()
        performance = raw['data']['characterData']['character']['performance']
        performance['allStars'] = [
            {'spec': 'Elemental', 'points': 800, 'rank': 10354},
            {'spec': 'Enhancement', 'points': 700, 'rank': 75615}]
        first = performance['rankings'][0]
        first.update(bestAmount=444.9, bestSpec='Elemental',
                     bestRank={'ilvl': 17, 'speed': -678436999},
                     allStars={'rank': 12445})
        # The score run is +17, while the uploaded DPS log is only +15.
        performance['throughputRankings']['12825']['best_level'] = 15
        second = copy.deepcopy(first)
        second.update(encounter={'id': 12813, 'name': 'Murder Row'},
                      bestAmount=440.8, bestSpec='Enhancement',
                      allStars={'rank': 23792})
        performance['rankings'].append(second)
        return raw

    def test_mixed_specs_use_best_score_per_dungeon_and_keep_raw_precision(self):
        profile = wcl.normalize(self.raw(), self.args())
        self.assertAlmostEqual(profile['score'], 885.7)
        self.assertEqual(profile['dungeons'][0]['points'], 444.9)
        self.assertEqual(len(profile['specRanks']), 2)

    def test_score_metadata_with_and_without_uploaded_throughput(self):
        profile = wcl.normalize(self.raw(), self.args())
        for row in profile['dungeons']:
            self.assertEqual(row['level'], 17)
            self.assertEqual(row['time'], '26:03')
        self.assertEqual(profile['dungeons'][0]['rank'], 12445)
        self.assertIsNone(profile['dungeons'][1]['amount'])

    def test_export_import_preserves_precision_total_rounding_and_truncates_dungeon_points(self):
        profile = wcl.normalize(self.raw(), self.args())
        self.assertEqual(self.mpl.Import(wcl.export(profile)), 1)
        self.mpl.ShowProfile('Киндрих', 'Гордунни')
        panel = self.mpl.panel
        self.assertEqual(panel.scoreValue.text, '886')
        self.assertAlmostEqual(panel.profile.score, 885.7)
        self.assertEqual(panel.rows[1].cells[2].text, 17)
        self.assertEqual(panel.rows[1].cells[3].text, '26:03')
        self.assertEqual(panel.rows[1].cells[5].text, '444')
        self.assertEqual(panel.rows[2].cells[5].text, '440')
        self.assertEqual(panel.profile.dungeons[1].points, 444.9)
        self.assertEqual(panel.rows[1].cells[6].text, 12445)
        self.assertEqual(panel.rows[2].cells[7].text, '—')

    def test_single_spec_preserves_wcl_total_without_recomputing(self):
        raw = self.raw()
        raw['data']['characterData']['character']['performance']['allStars'] = [
            {'spec': 'Elemental', 'points': 800.99}]
        self.assertEqual(wcl.normalize(raw, self.args('Elemental'))['score'], 800.99)

    def test_incomplete_score_data_does_not_become_partial_total(self):
        raw = self.raw()
        raw['data']['characterData']['character']['performance']['rankings'][0]['bestAmount'] = None
        self.assertIsNone(wcl.normalize(raw, self.args())['score'])

    def test_captured_score_run_time_and_rank(self):
        raw = json.loads((test_addon.ROOT / 'experiments/wcl-points-and-damage.json').read_text(encoding='utf-8'))
        row = wcl.normalize(raw, self.args())['dungeons'][0]
        self.assertEqual(row['level'], 19)
        self.assertEqual(row['time'], '29:26')
        self.assertEqual(row['rank'], 1314)


if __name__ == '__main__':
    unittest.main()
