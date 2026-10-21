"""WCL's low-sample Best percentile annotation survives both metric views."""
import copy
import json
from types import SimpleNamespace
import unittest

import test_addon
import wcl_sync as wcl


class LowParseMarkerTests(unittest.TestCase):
    def setUp(self):
        test_addon.AddonTests.setUp(self)

    def normalize(self, raw, metric='dps'):
        return wcl.normalize(raw, SimpleNamespace(realm='Гордунни', region='eu', zone=55,
            season='test', spec=None, metric=metric, server_slug=None))

    def raw(self, primary=True, secondary=False):
        raw = test_addon.api_fixture()
        char = raw['data']['characterData']['character']
        char['damage'] = char.pop('performance')
        char['healing'] = copy.deepcopy(char['damage'])
        char['damage']['throughputRankings']['12825']['best_historical_low_parses'] = primary
        char['healing']['throughputRankings']['12825']['best_historical_low_parses'] = secondary
        return raw

    def imported(self, profile, **options):
        self.assertEqual(self.mpl.Import(wcl.export(profile, **options)), 1)
        return self.mpl.GetProfile('Киндрих', 'Гордунни')[0]

    def test_captured_temple_marker_survives_normalize_export_import(self):
        raw = json.loads((test_addon.ROOT / 'experiments/wcl-points-and-damage.json').read_text(encoding='utf-8'))
        source = raw['data']['characterData']['character']['performance']['throughputRankings']['61877']
        self.assertIs(source['best_historical_low_parses'], True)
        profile = self.normalize(raw)
        temple = next(d for d in profile['dungeons'] if d['name'] == 'Temple of Sethraliss')
        self.assertIs(temple.get('flagged'), True)
        stored = self.imported(profile, rank_colors=True)
        received = next(d for d in stored.dungeons.values() if d.name == temple['name'])
        self.assertIs(received.flagged, True)
        self.assertEqual(received.best, 11)

    def test_metric_specific_markers_are_independent_and_zero_percent_is_valid(self):
        for primary, secondary in ((False, False), (True, False), (False, True), (True, True)):
            for metric in ('dps', 'hps'):
                with self.subTest(primary=primary, secondary=secondary, metric=metric):
                    raw = self.raw(primary, secondary)
                    raw['data']['characterData']['character']['damage']['throughputRankings']['12825']['best_historical_percentile'] = 0
                    profile = self.normalize(raw, metric)
                    row = self.imported(profile, rank_colors=True).dungeons[1]
                    expected = (primary, secondary) if metric == 'dps' else (secondary, primary)
                    self.assertEqual((row.flagged is True, row.otherFlagged is True), expected)
                    self.assertEqual(row.best if metric == 'dps' else row.otherBest, 0)

    def test_marker_only_extension_without_rank_or_spec(self):
        profile = self.normalize(self.raw())
        profile['dungeons'][0]['rankPercent'] = None
        for details in (False, True):
            with self.subTest(details=details):
                row = self.imported(profile, rank_colors=True, spec_details=details).dungeons[1]
                self.assertIs(row.flagged, True)
                self.assertIsNone(row.rankPercent)

    def test_missing_marker_and_legacy_output_do_not_invent_annotation(self):
        profile = self.normalize(self.raw())
        row = self.imported(profile).dungeons[1]
        self.assertIsNone(row.flagged)
        self.assertIsNone(row.otherFlagged)
        raw = self.raw()
        for metric in ('damage', 'healing'):
            del raw['data']['characterData']['character'][metric]['throughputRankings']['12825']['best_historical_low_parses']
        row = self.imported(self.normalize(raw), rank_colors=True).dungeons[1]
        self.assertIsNone(row.flagged)
        self.assertIsNone(row.otherFlagged)

    def test_invalid_api_marker_is_not_coerced_from_truthy_values(self):
        for value in (0, 1, 'true', 'false', [], {}):
            with self.subTest(value=value):
                raw = self.raw(primary=value)
                with self.assertRaises(wcl.ProfileError):
                    self.normalize(raw)

    def test_strict_annotation_mask_and_no_secondary_marker_in_single_profile(self):
        profile = self.normalize(self.raw())
        text = wcl.export(profile, rank_colors=True)
        for value in ('', '0', '4', '-1', '1.0', '01', 'true', '1,0'):
            with self.subTest(value=value):
                lines = text.splitlines()
                index = next(i for i, line in enumerate(lines) if line.startswith('D\t'))
                fields = lines[index].split('\t')
                self.assertEqual(len(fields), 17)
                fields[-1] = value
                lines[index] = '\t'.join(fields)
                self.assertIsNone(self.mpl.Parse('\n'.join(lines))[0])
        raw = test_addon.api_fixture()
        raw['data']['characterData']['character']['performance']['throughputRankings']['12825']['best_historical_low_parses'] = True
        text = wcl.export(self.normalize(raw), rank_colors=True)
        for value in ('2', '3'):
            lines = text.splitlines()
            index = next(i for i, line in enumerate(lines) if line.startswith('D\t'))
            fields = lines[index].split('\t')
            self.assertEqual(len(fields), 13)
            fields[-1] = value
            lines[index] = '\t'.join(fields)
            self.assertIsNone(self.mpl.Parse('\n'.join(lines))[0])

    def test_pending_secondary_cannot_claim_a_low_sample_result(self):
        profile = self.normalize(self.raw())
        profile.update(secondaryPending=True, role='DAMAGER', otherBest=None, otherMedian=None)
        row = profile['dungeons'][0]
        for key in ('otherLevel', 'otherAmount', 'otherBest', 'otherMedian'):
            row[key] = None
        self.assertEqual(self.imported(profile, rank_colors=True).dungeons[1].flagged, True)
        row['otherFlagged'] = True
        self.assertIsNone(self.mpl.Parse(wcl.export(profile, rank_colors=True))[0])


if __name__ == '__main__':
    unittest.main()
