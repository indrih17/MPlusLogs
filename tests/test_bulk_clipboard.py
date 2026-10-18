"""Bulk paste keeps protocol record boundaries instead of a huge native text line."""
import copy
import unittest
from unittest.mock import patch
from urllib.parse import quote, unquote

import test_batch
from test_addon import ROOT
import clipboard_protocol
import realm_resolver
import build_database as builder
import wcl_sync as wcl


class BulkClipboardTests(unittest.TestCase):
    def setUp(self):
        self.case = test_batch.BatchTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.lua, self.mpl = self.case.lua, self.case.mpl
        self.mpl.ShowProfile = lambda *args: None
        self.mapping = realm_resolver.load_mappings()

    def batch(self):
        profiles, players = [], []
        for index in range(100):
            entry = dict(name='Player' + chr(97 + index // 26) + chr(97 + index % 26),
                         realm='Гордунни', region='eu', server_slug='gordunni', spec='')
            profile = wcl.normalize(self.case.fetch(builder.arguments(entry)), builder.arguments(entry))
            dungeon = profile['dungeons'][0]
            profile['dungeons'] = [dict(copy.deepcopy(dungeon), name='Подземелье ' + str(i)) for i in range(8)]
            profiles.append(profile)
            players.append(self.lua.table_from(entry))
        _, request = self.mpl.SendBatchRequest(self.lua.table_from(players))
        body = 'MPL2\n' + ''.join(wcl.export(p).removeprefix('MPL1\n') for p in profiles)
        with patch.object(clipboard_protocol.bridge, 'process_request', return_value=(body, {})):
            reply = clipboard_protocol.reply(request, self.mapping, self.case.cache)
        return body, reply

    def test_100_profiles_keep_short_lines_and_exact_decoded_payload(self):
        body, reply = self.batch()
        payload = reply.split('MPLB1\n', 1)[1]
        # Structural guard for the native WoW paste bottleneck. This does not
        # measure the game engine; the live test window measures that separately.
        self.assertLess(max(map(len, payload.splitlines())), 2000)
        self.assertEqual(unquote(payload), body)
        self.assertNotIn('\t', reply)
        self.assertEqual(self.mpl.ReceiveReply(reply, True), 100)

    def test_published_addon_also_imports_multiline_batch(self):
        for name in ('Data.lua', 'Transport.lua', 'UI.lua'):
            self.lua.execute('return assert(loadstring(...))',
                             (ROOT / 'tests/compatibility/published-v1' / name).read_text(encoding='utf-8'))('MPlusLogs', self.mpl)
        _, reply = self.batch()
        self.assertEqual(self.mpl.ReceiveReply(reply.replace('\n', '\r\n'), True), 100)

    def test_literal_percent_and_field_newlines_stay_inside_their_field(self):
        _, request = self.mpl.SendRequest('Alice', 'Гордунни', 'dps', '')
        body = 'MPL1\nP\t' + wcl.line('x', '100%\nNext\tColumn') + '\nE\n'
        with patch.object(clipboard_protocol.bridge, 'process_request', return_value=(body, {})):
            reply = clipboard_protocol.reply(request, self.mapping, self.case.cache)
        self.assertEqual(unquote(reply.split('MPLB1\n', 1)[1]), body)


if __name__ == '__main__':
    unittest.main()
