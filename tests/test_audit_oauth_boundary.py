"""Malformed token replies must not escape the login recovery path."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import wcl_oauth as oauth


class OAuthBoundaryTests(unittest.TestCase):
    def test_non_ascii_callback_state_is_a_handled_rejection(self):
        with self.assertRaises(ValueError):
            oauth.callback_code('/callback?state=%E2%98%83&code=fixture', 'expected-state')

    def test_malformed_credentials_are_rejected_without_echoing_them(self):
        for token in ('private-token\r\nInjected: value', 'private-token\x00', 'private-token☃'):
            with self.subTest(token=repr(token)):
                for field in ('access_token', 'refresh_token'):
                    reply = dict(access_token='valid', expires_in=3600, refresh_token='valid-refresh')
                    reply[field] = token
                    with self.assertRaises(ValueError) as failure:
                        oauth.token_record(reply)
                    self.assertNotIn('private-token', str(failure.exception))

    def test_invalid_expiry_is_a_handled_login_error(self):
        for lifetime in (float('inf'), float('nan'), 10**400, True, '999999999999999999999999'):
            with self.subTest(lifetime=str(lifetime)), self.assertRaises(ValueError):
                oauth.token_record(dict(access_token='fixture', expires_in=lifetime))

    def test_bad_refresh_reply_cannot_replace_session_credentials(self):
        original = dict(access_token='expired', refresh_token='valid-refresh', expires_at=0)
        saved = []
        session = oauth.Session('fixture-client', original, saved.append)
        with patch.object(oauth, 'exchange', return_value=dict(access_token='new', refresh_token={'bad': 'shape'}, expires_in=3600)):
            with self.assertRaises(ValueError):
                session.access_token()
        self.assertEqual(session.tokens, original)
        self.assertEqual(saved, [])
