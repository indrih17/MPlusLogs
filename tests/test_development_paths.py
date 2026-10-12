"""Publisher metadata cannot live inside a Battle.net-managed game folder."""
from pathlib import Path
import tempfile
import unittest
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from development_paths import build_tools_dir


class DevelopmentPathTests(unittest.TestCase):
    def test_default_git_location_is_outside_game(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-paths-') as directory:
            base=Path(directory)
            source=base/'World of Warcraft/_retail_/Interface/AddOns/MPlusLogs'
            data=base/'LocalAppData'
            destination=build_tools_dir(source,{'LOCALAPPDATA':str(data)})
            self.assertEqual(destination,data/'MPlusLogsDevelopment/build-tools')
            self.assertFalse(destination.is_relative_to(base/'World of Warcraft'))

    def test_override_anywhere_in_game_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-paths-') as directory:
            game=Path(directory)/'World of Warcraft'
            source=game/'_retail_/Interface/AddOns/MPlusLogs'
            for path in [source,game/'Data',game/'OtherDevelopmentFolder']:
                with self.assertRaises(ValueError):
                    build_tools_dir(source,{'MPLUSLOGS_DEVELOPMENT_HOME':str(path)})

    def test_explicit_external_override_is_supported(self):
        with tempfile.TemporaryDirectory(prefix='mpluslogs-paths-') as directory:
            source=Path(directory)/'source'
            external=Path(directory)/'development'
            self.assertEqual(build_tools_dir(source,{'MPLUSLOGS_DEVELOPMENT_HOME':str(external)}),external/'build-tools')

if __name__=='__main__': unittest.main()
