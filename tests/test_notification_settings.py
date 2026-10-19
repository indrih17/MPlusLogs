"""Popup notifications persist separately from reply sounds."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import local_settings
import companion_i18n


class NotificationSettingsTests(unittest.TestCase):
    def test_notifications_and_sound_round_trip_independently(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path=Path(folder)/'settings.json'
            with patch.object(local_settings,'PATH',path):
                for notifications in (False,True):
                    for sound in (False,True):
                        with self.subTest(notifications=notifications,sound=sound):
                            local_settings.save_config({'notifications':notifications,'sound':sound})
                            stored=json.loads(path.read_text(encoding='utf-8'))
                            self.assertIs(stored['notifications'],notifications)
                            self.assertIs(stored['sound'],sound)
                            loaded=local_settings.load()
                            self.assertIs(loaded['notifications'],notifications)
                            self.assertIs(loaded['sound'],sound)

    def test_legacy_config_keeps_notifications_absent_for_gui_default(self):
        for config in ({},{'sound':False},{'sound':True}):
            with self.subTest(config=config):
                validated=local_settings.validate_config(config)
                self.assertNotIn('notifications',validated)
                self.assertEqual(validated,config)

    def test_non_boolean_notifications_are_dropped_without_changing_sound(self):
        for invalid in (None,0,1,'false',[],{}):
            with self.subTest(invalid=invalid):
                self.assertEqual(local_settings.validate_config(
                    {'notifications':invalid,'sound':False,'theme':'dark'}),
                    {'sound':False,'theme':'dark'})

    def test_invalid_saved_notification_value_is_ignored_on_load(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path=Path(folder)/'settings.json'
            path.write_text(json.dumps({'notifications':'false','sound':True}),encoding='utf-8')
            with patch.object(local_settings,'PATH',path):
                self.assertEqual(local_settings.load(),{'sound':True})

    def test_notification_label_is_present_in_every_locale(self):
        for language in companion_i18n.LANGUAGES:
            with self.subTest(language=language):
                translated=companion_i18n.catalog(language).get('Всплывающие уведомления')
                self.assertTrue(translated)


if __name__=='__main__': unittest.main()
