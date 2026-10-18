"""Sixty real builder/cache exports survive a mixed-result Lua import."""
import unittest

import test_batch
import clipboard_protocol
import realm_resolver
import wcl_sync as wcl


class BulkRoundtripAuditTests(unittest.TestCase):
    def test_sixty_members_keep_successes_and_individual_failures(self):
        case = test_batch.BatchTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        names = ['Player' + chr(97 + i // 26) + chr(97 + i % 26) for i in range(60)]
        hidden = set(names[::8])
        players = case.lua.table_from([case.lua.table_from(dict(name=name, realm='Гордунни', role='DAMAGER'))
                                       for name in names])
        case.mpl.ShowProfile = lambda *args: None
        _, request = case.mpl.SendBatchRequest(players)
        calls = []

        def fetch(args):
            calls.append(args.name)
            if args.name in hidden:
                raise wcl.NoProfile('Rankings hidden', 'hidden')
            return case.fetch(args)

        reply = clipboard_protocol.reply(request, realm_resolver.load_mappings(), case.cache, fetch)
        self.assertEqual(case.mpl.ReceiveReply(reply, True), len(names) - len(hidden))
        self.assertEqual(set(calls), set(names))
        self.assertEqual(len(calls), 60)
        self.assertEqual(len(list(case.mpl.lastBatchResult.failures.values())), len(hidden))
        for name in names:
            result = case.mpl.GetProfile(name, 'Гордунни')
            profile = result[0] if isinstance(result, tuple) else result
            if name in hidden:
                self.assertIsNone(profile)
                self.assertEqual(case.mpl.GetProfileState(name, 'Гордунни', '').reason, 'hidden')
            else:
                self.assertEqual(profile.name, name)
                self.assertGreater(profile.runs, 0)
