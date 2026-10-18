"""Quota savings must preserve secondary metrics and complete cache semantics."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests"), str(ROOT / ".test-deps")]
from test_addon import api_fixture
import test_addon
import build_database as builder
import wcl_sync as wcl


def raw_profile(class_id=8, partial=False, class_name=None):
    raw = copy.deepcopy(api_fixture())
    char = raw["data"]["characterData"]["character"]
    char["classID"] = class_id
    raw["data"]["gameData"] = {"classes": [{"id": class_id, "name": class_name or ("Mage" if class_id == 8 else "Druid")}]}
    char["damage"] = char.pop("performance")
    char["damage"]["rankings"][0]["bestSpec"] = "Fire" if class_id == 8 else "Guardian"
    if partial:
        raw[wcl.PRIMARY_ONLY_MARKER] = 1
    else:
        char["healing"] = copy.deepcopy(char["damage"])
        char["healing"]["bestPerformanceAverage"] = 91
    return raw


class PrimaryMetricTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-work-")
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.entry = dict(name="Киндрих", realm="Гордунни", server_slug="gordunni", region="eu")

    def args(self, **kwargs):
        return builder.arguments(dict(self.entry, **kwargs))

    def test_request_only_known_pure_classes_and_unambiguous_specs(self):
        for class_id in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 51, 70, None):
            self.assertFalse(wcl.primary_only_request(self.args(class_id=class_id)))
        self.assertTrue(wcl.primary_only_request(self.args(class_name="MAGE")))
        self.assertTrue(wcl.primary_only_request(self.args(spec="Fire")))
        self.assertTrue(wcl.primary_only_request(self.args(spec="Frost")))
        self.assertTrue(wcl.primary_only_request(self.args(spec="Feral", class_id=11)))
        self.assertFalse(wcl.primary_only_request(self.args(spec="Unknown")))
        for spec in ('Guardian','Holy','Blood','Restoration'):
            self.assertFalse(wcl.primary_only_request(self.args(spec=spec,role='DAMAGER')))
        for extra in (dict(metric="hps"), dict(role="HEALER"), dict(role="TANK"), dict(include_secondary=True)):
            self.assertFalse(wcl.primary_only_request(self.args(class_id=8, **extra)))

    def test_graphql_includes_secondary_by_request(self):
        for extra, include in ((dict(class_name="Mage"), False), (dict(class_id=11), True), (dict(class_name="Mage", metric="hps"), True)):
            raw = raw_profile(partial=not include)
            raw.pop(wcl.PRIMARY_ONLY_MARKER, None)
            with patch.object(wcl, "request_json", return_value=raw) as request:
                result = wcl.fetch(self.args(**extra), token="test")
            variables = json.loads(request.call_args.args[1])["variables"]
            self.assertEqual(variables["includeHealing"], include)
            self.assertEqual(wcl.primary_only_raw(result), not include)
            self.assertEqual(request.call_count, 1)

    def test_partial_marker_required_and_actual_class_verified(self):
        raw = raw_profile(partial=True)
        raw.pop(wcl.PRIMARY_ONLY_MARKER)
        with self.assertRaises(wcl.ProfileError):
            wcl.normalize(raw, self.args())
        with self.assertRaises(wcl.ProfileError):
            wcl.normalize(raw_profile(0, partial=True), self.args())
        with patch.object(wcl, "request_json", return_value=raw_profile(0, partial=True)) as request:
            with self.assertRaises(wcl.ProfileError):
                wcl.fetch(self.args(class_name="Mage"), token="test")
            self.assertEqual(request.call_count, 1)

    def test_stale_class_name_hint_cannot_reduce_an_unknown_hybrid_role(self):
        raw=raw_profile(9,partial=True,class_name='Shaman')
        raw.pop(wcl.PRIMARY_ONLY_MARKER)
        with patch.object(wcl,'request_json',return_value=raw) as request:
            with self.assertRaisesRegex(wcl.ProfileError,'Class changed'):
                wcl.fetch(self.args(class_name='Mage'),token='test')
        self.assertEqual(request.call_count,1)

    def test_every_current_damage_role_can_omit_healing(self):
        for class_id in [*range(1, 14), 51, 70]:
            args = self.args(class_id=class_id, role="DAMAGER")
            self.assertTrue(wcl.primary_only_request(args))
            raw = raw_profile(class_id, partial=True)
            # Prior logged healer/tank specs must not override current DPS role.
            profile = wcl.normalize(raw, args)
            self.assertEqual(profile["role"], "DAMAGER")
            self.assertEqual(profile["metric"], "dps")
            self.assertTrue(profile["dual"])
            self.assertTrue(profile["secondaryPending"])
            self.assertEqual(wcl.normalize(raw, self.args())["role"], "DAMAGER")
            raw.pop(wcl.PRIMARY_ONLY_MARKER)
            with patch.object(wcl, "request_json", return_value=raw) as request:
                wcl.fetch(args, token="test")
            self.assertFalse(json.loads(request.call_args.args[1])["variables"]["includeHealing"])

    def test_tank_and_healer_roles_override_contradictory_hints(self):
        for role in ("TANK", "HEALER"):
            args = self.args(class_id=8, spec="Fire", role=role)
            self.assertFalse(wcl.primary_only_request(args))
            with self.assertRaises(wcl.ProfileError):
                wcl.normalize(raw_profile(partial=True), args)
            self.assertFalse(wcl.cache_satisfies(raw_profile(partial=True), args))

    def test_unknown_hybrid_role_upgrades_partial_cache(self):
        path = builder.cache_path(self.cache, self.entry)
        builder.atomic_write(path, json.dumps(dict(fetched_at=100000, raw=raw_profile(11, partial=True))))
        calls = []
        def fetch(args):
            calls.append(args)
            return raw_profile(11)
        profiles, report = builder.build([self.entry], self.cache, fetcher=fetch, now=100001)
        self.assertEqual(report["fetched"], 1)
        self.assertFalse(wcl.primary_only_request(calls[0]))
        self.assertFalse(profiles[0]["secondaryPending"])

    def test_wcl_class_mapping_controls_fallback_with_shuffled_ids(self):
        for class_id, name, pure in ((9, "Shaman", False), (10, "Warlock", True), (51, "Warrior", False), (70, "Monk", False), (812, "Mage", True)):
            raw = raw_profile(class_id, class_name=name)
            character = raw["data"]["characterData"]["character"]
            character["damage"]["rankings"][0]["bestSpec"] = "Unknown"
            self.assertEqual(wcl.character_class_name(raw), name.casefold())
            inferred = wcl.normalize(raw, self.args(metric="hps"))
            self.assertEqual(inferred["role"], "DAMAGER" if pure else "HEALER")
            path = builder.cache_path(self.cache, self.entry)
            builder.atomic_write(path, json.dumps(dict(fetched_at=100000, raw=raw)))
            calls = []
            def fetch(args):
                calls.append(args)
                return raw
            builder.build([self.entry], self.cache, fetcher=fetch, now=200000)
            self.assertEqual(calls[0].class_name, name.casefold())
            self.assertEqual(wcl.primary_only_request(calls[0]), pure)
        raw = raw_profile(10, class_name="Warlock")
        raw["data"].pop("gameData")
        self.assertIsNone(wcl.character_class_name(raw))

    def test_partial_export_preserves_primary_spec_and_unknown_secondary(self):
        profile = wcl.normalize(raw_profile(partial=True), self.args())
        self.assertTrue(profile["dual"])
        self.assertTrue(profile["secondaryPending"])
        self.assertEqual(profile["primarySpec"], "Fire")
        self.assertIsNone(profile["otherBest"])
        self.assertIsNone(profile["dungeons"][0]["otherAmount"])
        # Exercise the actual Lua protocol parser, not only Python serialization.
        addon = test_addon.AddonTests()
        addon.setUp()
        parsed = addon.mpl.Parse(wcl.export(profile))
        self.assertNotIsInstance(parsed, tuple)
        imported = list(parsed.values())
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["primarySpec"], "Fire")
        self.assertTrue(imported[0]["dual"])
        self.assertTrue(imported[0]["secondaryPending"])
        self.assertEqual(imported[0]["role"], "DAMAGER")

    def test_tank_healing_and_healer_damage_stay_dual(self):
        for role, metric in (("TANK", "dps"), ("HEALER", "hps")):
            profile = wcl.normalize(raw_profile(11), self.args(role=role))
            self.assertTrue(profile["dual"])
            self.assertEqual(profile["metric"], metric)
            self.assertIsNotNone(profile["dungeons"][0]["otherAmount"])
        profile = wcl.normalize(raw_profile(), self.args(metric="hps", role="DAMAGER"))
        self.assertEqual(profile["metric"], "dps")

    def test_full_cache_reuse_and_partial_upgrade(self):
        calls = []
        def full(args):
            calls.append(args)
            return raw_profile()
        builder.build([self.entry], self.cache, fetcher=full, now=100000)
        _, report = builder.build([dict(self.entry, class_id=8)], self.cache, fetcher=full, now=100001)
        self.assertEqual(report["cacheHits"], 1)
        self.assertEqual(len(calls), 1)
        path = builder.cache_path(self.cache, self.entry)
        builder.atomic_write(path, json.dumps(dict(fetched_at=100000, raw=raw_profile(partial=True))))
        profiles, report = builder.build([dict(self.entry, metric="hps", role="DAMAGER")], self.cache, fetcher=full, now=100002)
        self.assertEqual(report["fetched"], 1)
        self.assertTrue(profiles[0]["dual"])
        self.assertEqual(calls[-1].class_id, 8)

    def test_malformed_partial_does_not_replace_full_cache(self):
        builder.build([self.entry], self.cache, fetcher=lambda _: raw_profile(), now=100000)
        bad = raw_profile(partial=True)
        bad.pop(wcl.PRIMARY_ONLY_MARKER)
        profiles, report = builder.build([self.entry], self.cache, fetcher=lambda _: bad, now=100301, refresh=True)
        self.assertTrue(report["errors"])
        self.assertTrue(profiles[0]["dual"])
        cached = builder.read_cache(builder.cache_path(self.cache, self.entry))
        self.assertIn("healing", cached["raw"]["data"]["characterData"]["character"])

    def test_incomplete_upgrade_cannot_replace_previous_full_cache(self):
        entry=dict(self.entry,metric='hps',role='DAMAGER')
        builder.build([entry],self.cache,fetcher=lambda _:raw_profile(),now=100000)
        profiles,report=builder.build([entry],self.cache,
            fetcher=lambda _:raw_profile(partial=True),now=100301,refresh=True)
        self.assertTrue(report['errors'])
        self.assertFalse(profiles[0]['secondaryPending'])
        cached=builder.read_cache(builder.cache_path(self.cache,entry))
        self.assertIn('healing',cached['raw']['data']['characterData']['character'])

    def test_empty_primary_is_not_negative_cached_and_next_fetch_is_full(self):
        raw = raw_profile(partial=True)
        raw["data"]["characterData"]["character"]["damage"]["throughputRankings"] = {}
        profiles, report = builder.build([self.entry], self.cache, fetcher=lambda _: raw, now=100000)
        self.assertEqual(profiles, [])
        cached = builder.read_cache(builder.cache_path(self.cache, self.entry))
        self.assertFalse(cached.get("negative", False))
        calls = []
        def fetch(args):
            calls.append(args)
            return raw_profile()
        builder.build([self.entry], self.cache, fetcher=fetch, now=100301)
        self.assertTrue(calls[0].include_secondary)


if __name__ == "__main__":
    unittest.main()
