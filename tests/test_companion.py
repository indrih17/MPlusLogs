"""Optional clipboard bridge checks; no OS clipboard or network access."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "tools"))
import clipboard_companion as companion
import realm_resolver
from test_addon import api_fixture


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".test-work-",dir=ROOT)
        self.directory = Path(self.temp.name)
        self.assertTrue(self.directory.resolve().is_relative_to(ROOT.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.mapping = realm_resolver.load_mappings()
        self.request = "MPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\tGuardian\n"

    def test_cross_realm_resolution_without_manual_roster(self):
        for name in ("Silvermoon","Tarren Mill","Twisting Nether","Азурегос"):
            slug = realm_resolver.resolve(self.mapping,"eu",name)
            self.assertTrue(slug)
        self.assertEqual(realm_resolver.resolve(self.mapping,"eu","Ткач Смерти"),"ткач-смерти")

    def test_query_and_response_preserve_spec(self):
        called = []
        def fetch(args):
            called.append(args)
            return api_fixture()
        response, report = companion.process_request(self.request,self.mapping,self.directory,fetcher=fetch)
        self.assertTrue(response.startswith("MPL1\nP\t"))
        self.assertEqual(called[0].spec,"Guardian")
        self.assertEqual(called[0].server_slug,"gordunni")
        self.assertEqual(report["profiles"],1)

    def test_non_mpl_clipboard_cannot_trigger_network(self):
        def forbidden(_):
            raise AssertionError("Must not transmit unrelated clipboard text")
        with self.assertRaises(ValueError):
            companion.process_request("unrelated clipboard text",self.mapping,self.directory,fetcher=forbidden)

    def test_changed_clipboard_preserved_and_reply_saved(self):
        class Clipboard:
            text = "something else copied while fetching"
            def reply_if_unchanged(self,expected,response):
                if self.text != expected:
                    return False
                self.text = response
                return True
        clipboard = Clipboard()
        args = SimpleNamespace(cache=self.directory,offline=False,ttl_hours=1,output=self.directory / "result.mpl")
        companion.deliver(self.request,clipboard,self.mapping,args,lambda _:api_fixture())
        self.assertEqual(clipboard.text,"something else copied while fetching")
        self.assertTrue(args.output.read_text(encoding="utf-8").startswith("MPL1\n"))


if __name__ == "__main__":
    unittest.main()
