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

    def test_first_launch_enables_popups_for_new_and_existing_users(self):
        for previous in (None,{}, {'notifications':False,'sound':False}, {'notifications':True}):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory(dir=ROOT) as folder:
                path=Path(folder)/'settings.json'
                if previous is not None:
                    path.write_text(json.dumps(previous),encoding='utf-8')
                with patch.object(local_settings,'PATH',path):
                    migrated=local_settings.initialize_notifications(local_settings.load())
                    self.assertIs(migrated['notifications'],True)
                    self.assertIs(migrated['notifications_initialized'],True)
                    self.assertEqual(local_settings.load(),migrated)
                    if previous and 'sound' in previous:
                        self.assertIs(migrated['sound'],False)

    def test_disabling_after_migration_survives_next_launch_without_rewrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path=Path(folder)/'settings.json'
            with patch.object(local_settings,'PATH',path):
                config=local_settings.initialize_notifications({})
                config['notifications']=False
                local_settings.save_config(config)
                saved=path.read_bytes()
                with patch.object(local_settings,'_write_config') as write:
                    loaded=local_settings.initialize_notifications(local_settings.load())
                self.assertIs(loaded['notifications'],False)
                self.assertIs(loaded['notifications_initialized'],True)
                self.assertEqual(path.read_bytes(),saved)
                write.assert_not_called()

    def test_migration_preserves_encrypted_credentials_and_other_fields(self):
        stored={'oauth_dpapi':'unchanged encrypted token','secret_dpapi':'legacy encrypted token',
                'theme':'dark','language':'enUS','notifications':False,'future_field':42}
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path=Path(folder)/'settings.json'
            path.write_text(json.dumps(stored),encoding='utf-8')
            with patch.object(local_settings,'PATH',path),patch.object(local_settings,'crypt') as crypt:
                local_settings.initialize_notifications({'notifications':False})
                crypt.assert_not_called()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),
                             dict(stored,notifications=True,notifications_initialized=True))

    def test_corrupt_file_is_not_overwritten_or_marked_migrated(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path=Path(folder)/'settings.json'
            path.write_text('{broken',encoding='utf-8')
            with patch.object(local_settings,'PATH',path):
                with self.assertRaises(ValueError):
                    local_settings.initialize_notifications({})
            self.assertEqual(path.read_text(encoding='utf-8'),'{broken')

    def test_failed_migration_write_can_be_retried(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path=Path(folder)/'settings.json'
            path.write_text('{"notifications":false}',encoding='utf-8')
            config={'notifications':False}
            with patch.object(local_settings,'PATH',path):
                with patch.object(local_settings,'_write_config',side_effect=OSError('read-only')):
                    with self.assertRaises(OSError):
                        local_settings.initialize_notifications(config)
                self.assertEqual(config,{'notifications':False})
                self.assertEqual(local_settings.load(),config)
                self.assertIs(local_settings.initialize_notifications(config)['notifications'],True)

    def test_explicit_installer_choice_overrides_old_value_and_skips_migration(self):
        for enabled in (False,True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(dir=ROOT) as folder:
                path=Path(folder)/'settings.json'
                path.write_text(json.dumps({'notifications':not enabled,'sound':False}),encoding='utf-8')
                with patch.object(local_settings,'PATH',path):
                    local_settings.set_notifications(enabled)
                    loaded=local_settings.initialize_notifications(local_settings.load())
                self.assertIs(loaded['notifications'],enabled)
                self.assertIs(loaded['notifications_initialized'],True)
                self.assertIs(loaded['sound'],False)


if __name__=='__main__': unittest.main()
