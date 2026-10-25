"""The Companion release must recover with the unchanged published 0.5.x addon."""
import time
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import test_batch
import clipboard_companion as bridge
import clipboard_protocol
import build_database as builder
import realm_resolver
import wcl_sync as wcl


class LegacyBatchCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.case = test_batch.BatchTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.lua, self.mpl = self.case.lua, self.case.mpl
        self.now = int(time.time())
        self.lua.globals().GetServerTime = lambda: self.now
        self.mpl.companionInfo = self.lua.table_from(dict(
            version='1.0.30', capabilities=self.lua.table_from(dict(errorcodes=True))))
        self.client = bridge.Client(token_provider=lambda: 'offline-token')
        self.client.budget.clock = lambda: self.now
        self.addCleanup(self.client.budget.close)
        self.mapping = realm_resolver.load_mappings()

    def exchange(self):
        _, request = self.mpl.SendBatchRequest(self.case.players())
        with patch.object(builder.time, 'time', return_value=self.now):
            reply = clipboard_protocol.reply(request, self.mapping, self.case.cache, self.client)
        return self.mpl.ReceiveReply(reply, True), reply

    def test_legacy_addon_recovers_after_short_network_pause(self):
        calls = []

        def upstream(args, token, endpoint):
            calls.append(args.name)
            if len(calls) == 1:
                raise wcl.APIError('Could not connect to Warcraft Logs', code='network')
            raw = self.case.fetch(type('Args', (), dict(name='Alice'))())
            raw['data']['characterData']['character']['name'] = args.name
            return raw

        with patch.object(wcl, 'fetch', side_effect=upstream):
            imported, failed_reply = self.exchange()
            self.assertEqual(imported, 0)
            failed = clipboard_protocol.reply_summary(failed_reply)
            self.assertEqual(failed['available'], 0)
            self.assertEqual(failed['failed'], 2)
            original_retry = self.now + 15
            self.assertIn('MPLERR1%20network%20' + str(original_retry),
                          unquote(failed_reply.split('MPLB1\n', 1)[1]))
            self.now += 5
            imported, _ = self.exchange()
            self.assertEqual(imported, 0)
            self.assertEqual(len(calls), 1)
            self.now = original_retry
            imported, good_reply = self.exchange()
        self.assertEqual(imported, 2)
        self.assertEqual(len(calls), 3)
        self.assertEqual(clipboard_protocol.reply_summary(good_reply)['available'], 2)
        self.assertIsNone(self.mpl.pendingReply)


if __name__ == '__main__':
    unittest.main()
