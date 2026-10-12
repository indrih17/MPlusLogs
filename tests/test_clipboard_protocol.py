from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "tools"))
import clipboard_protocol as protocol
import realm_resolver
from test_addon import api_fixture


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix=".test-work-",dir=ROOT)
        self.path=Path(self.temp.name)
        self.assertTrue(self.path.resolve().is_relative_to(ROOT.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.request="MPLS1\n12345-1\nMPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\tGuardian\n"
        self.mapping=realm_resolver.load_mappings()

    def test_unrelated_text_and_own_reply_are_ignored(self):
        for text in ("a password or unrelated text","MPLS1\n12345-1\nMPL1\nP\t...","MPLE1\n12345-1\nerror"):
            self.assertIsNone(protocol.unwrap_request(text))
            self.assertIsNone(protocol.reply(text,self.mapping,self.path,lambda _:self.fail("Unexpected network request")))

    def test_diagnostics_do_not_store_clipboard_contents(self):
        self.assertEqual(protocol.describe_clipboard("private unrelated text"),{"kind":"other"})
        self.assertEqual(protocol.describe_clipboard(self.request)["request_id"],"12345-1")
        event=protocol.describe_clipboard("MPLQ1\nQ\teu\tprivate realm\tprivate name")
        self.assertEqual(event["kind"],"mplus_unrecognized")
        self.assertNotIn("private",str(event))

    def test_diagnostic_preserves_request_id_without_network(self):
        reply=protocol.reply(self.request,self.mapping,self.path,lambda _:self.fail("Unexpected network request"),True)
        self.assertTrue(reply.startswith("MPLE1\n12345-1\n"))

    def test_real_response_envelope_has_same_id(self):
        reply=protocol.reply(self.request,self.mapping,self.path,lambda _:api_fixture())
        self.assertTrue(reply.startswith("MPLS1\n12345-1\nMPLB1\nMPL1%0AP%09"))
        self.assertNotIn("\t",reply)

    def test_network_failure_is_returned_to_addon(self):
        def fail(_): raise ValueError("HTTP 429")
        reply=protocol.reply(self.request,self.mapping,self.path,fail)
        self.assertTrue(reply.startswith("MPLE1\n12345-1\n"))
        self.assertIn("HTTP%20429",reply)


if __name__=="__main__": unittest.main()
