"""Failed WCL batches cross the real builder, envelope and addon paste handler."""
import time
import unittest
from unittest.mock import patch

import test_batch
import clipboard_protocol
import realm_resolver
import build_database as builder
import wcl_sync as wcl
import clipboard_companion as bridge


class FailedBatchRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.case = test_batch.BatchTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.lua, self.mpl = self.case.lua, self.case.mpl
        self.now = int(time.time())
        self.lua.globals().GetServerTime = lambda: self.now
        self.mpl.companionInfo = self.lua.table_from(dict(
            version='1.0.30', capabilities=self.lua.table_from(dict(errorcodes=True))))
        self.mapping = realm_resolver.load_mappings()

    def import_reply(self, fetch):
        self.mpl.ShowBatchDownload()
        frame = self.mpl.downloadWindow
        with patch.object(builder.time, 'time', return_value=self.now):
            reply = clipboard_protocol.reply(frame.request, self.mapping, self.case.cache, fetch)
        self.assertTrue(reply.startswith('MPLS1\n'), reply[:100])
        frame.edit.SetText(frame.edit, reply)
        frame.edit.scripts.OnTextChanged(frame.edit, True)
        self.case.flush()
        return frame, reply

    def test_failed_batch_is_visible_and_retry_matches_backend_cache(self):
        attempts = []

        def unavailable(args):
            attempts.append(args.name)
            raise wcl.APIError('WCL GraphQL error; inspect API schema/query. No export written',
                               code='schema', retry_after=60)

        frame, _ = self.import_reply(unavailable)
        self.assertEqual(self.mpl.lastBatchResult.count, 0)
        self.assertIsNotNone(self.mpl.batchResultsWindow)
        self.assertTrue(self.mpl.batchResultsWindow.shown)
        self.assertNotEqual(frame.status.text, self.mpl.L['Логи получены.'])
        for name in ('Alice', 'Bob'):
            state = self.mpl.GetProfileState(name, 'Гордунни', '')
            self.assertEqual(state.reason, 'retry')
            self.assertGreater(state.expires, self.now)
        first = self.mpl.GetProfileState('Alice', 'Гордунни', '')
        cached = builder.read_cache(builder.cache_path(self.case.cache, dict(
            name='Alice', realm='Гордунни', region='eu', server_slug='gordunni',
            spec=None, include_secondary=True, _cache_scope='public')))
        self.assertIsNotNone(cached)
        self.assertGreaterEqual(first.expires, cached['retry_until'])
        self.assertLessEqual(len(attempts), 2)

    def test_mixed_response_keeps_good_profile_and_surfaces_failed_identity(self):
        frame, _ = self.import_reply(self.case.fetch)
        self.assertEqual(self.mpl.lastBatchResult.count, 1)
        self.assertIsNotNone(self.mpl.GetProfile('Alice', 'Гордунни')[0])
        self.assertTrue(self.mpl.batchResultsWindow.shown)
        self.assertIn('1 из 2', self.mpl.batchResultsWindow.summary.text)
        self.assertIn('скрыты', self.mpl.batchResultsWindow.rows[2].status.text)
        self.assertNotEqual(frame.status.text, self.mpl.L['Логи получены.'])

    def test_real_client_network_failure_recovers_after_fifteen_seconds(self):
        client = bridge.Client(token_provider=lambda: 'offline-token')
        client.budget.clock = lambda: self.now
        self.addCleanup(client.budget.close)
        calls = []

        def upstream(args, token, endpoint):
            calls.append(args.name)
            if len(calls) == 1:
                raise wcl.APIError('Could not connect to Warcraft Logs', code='network')
            raw = self.case.fetch(type('Args', (), dict(name='Alice'))())
            raw['data']['characterData']['character']['name'] = args.name
            return raw

        with patch.object(wcl, 'fetch', side_effect=upstream):
            self.import_reply(client)
            state = self.mpl.GetProfileState('Alice', 'Гордунни', '')
            self.assertEqual(state.expires, self.now + 15)
            self.now += 15
            self.import_reply(client)
        self.assertEqual(self.mpl.lastBatchResult.loaded, 2)
        self.assertEqual(self.mpl.lastBatchResult.errorCount, 0)
        self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()
