"""Warcraft Logs table labels in each supported client locale."""
import json
import unittest

import test_localization


class ProfileLabelTests(unittest.TestCase):
    def test_reference_russian_and_english_table_copy(self):
        keys = ["Runs", "Rank", "Score", "Best DPS", "Best HPS", "DPS by Level", "HPS by Level"]
        references = {
            "ruRU": ["Runs", "Ранг", "Оценка", "Best DPS", "Best HPS", "DPS by Level", "HPS by Level"],
            "enUS": keys,
        }
        for locale, expected in references.items():
            with self.subTest(locale=locale):
                dictionary = json.loads((test_localization.ROOT / "Locales" / f"{locale}.json").read_text(encoding="utf-8"))
                self.assertEqual([dictionary[key] for key in keys], expected)

    def test_localized_profile_labels_follow_selected_metric(self):
        for locale in test_localization.LOCALES:
            with self.subTest(locale=locale):
                _, mpl = test_localization.LocalizationTests().runtime(locale)
                mpl.ShowProfile("Киндрих", "Гордунни")
                panel = mpl.panel
                for metric in ("dps", "hps"):
                    with self.subTest(metric=metric):
                        panel.metricTabs[metric].scripts.OnClick()
                        metric_name = metric.upper()
                        expected_keys = ["Подземелье", "Уровень", "Время", "Runs", "Очки", "Rank",
                                         f"Best {metric_name}", "Best %", "Median %"]
                        self.assertEqual([panel.headings[i].text for i in range(1, 10)],
                                         [mpl.L[key] for key in expected_keys])
                        self.assertEqual(panel.primaryGroup.text, mpl.L["Score"])
                        self.assertEqual(panel.secondaryGroup.text, mpl.L[f"{metric_name} by Level"])


if __name__ == "__main__":
    unittest.main()
