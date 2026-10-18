"""Loading progress follows real work, including cache, failures and extra specs."""
import copy
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_addon import ROOT, api_fixture
sys.path.insert(0, str(ROOT / 'tools'))
import clipboard_protocol
import companion_i18n as i18n
import realm_resolver


class LoadingProgressTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='.test-work-', dir=ROOT)
        self.addCleanup(folder.cleanup)
        self.cache = Path(folder.name)
        self.mapping = realm_resolver.load_mappings()

    def test_batch_counts_cached_and_failed_characters_without_extra_queries(self):
        request = 'MPLS1\n123-1\nMPLQ2\n' + ''.join(
            f'Q\teu\tГордунни\t{name}\tdps\tGuardian\n' for name in ('Киндрих', 'Missing'))
        events, calls = [], []
        def fetch(args):
            calls.append(args.name)
            self.assertEqual(events[-1]['completed'], len(calls) - 1)
            if args.name == 'Missing':
                raise ValueError('HTTP 429')
            return api_fixture()
        first = clipboard_protocol.reply(request, self.mapping, self.cache, fetch, progress=events.append)
        self.assertTrue(first.startswith('MPLS1\n'))
        self.assertEqual([e['completed'] for e in events], [0, 1, 2])
        self.assertEqual(events[1]['character'], 'Missing')
        events.clear()
        second = clipboard_protocol.reply(request, self.mapping, self.cache,
            lambda _: self.fail('Cached/cooling-down entries must not query WCL'), progress=events.append)
        self.assertTrue(second.startswith('MPLS1\n'))
        self.assertEqual([e['completed'] for e in events], [0, 1, 2])

    def test_specializations_have_their_own_real_total(self):
        request = ('MPLS2\n123-1\nMPLC1 specprofiles\nMPLQ1\n'
                   'Q\teu\tГордунни\tКиндрих\tdps\tGuardian\n')
        events = []
        def fetch(args):
            raw = copy.deepcopy(api_fixture())
            performance = raw['data']['characterData']['character']['performance']
            performance['allStars'] = [{'spec': spec, 'points': 3774} for spec in ('Guardian', 'Feral')]
            return raw
        reply = clipboard_protocol.reply(request, self.mapping, self.cache, fetch, progress=events.append)
        self.assertTrue(reply.startswith('MPLS1\n'), reply)
        for stage in ('profiles', 'overview', 'specializations'):
            part = [e for e in events if e['stage'] == stage]
            self.assertTrue(part, stage)
            self.assertEqual(part[0]['completed'], 0)
            self.assertEqual(part[-1]['completed'], part[-1]['total'])
        self.assertEqual(next(e for e in events if e['stage'] == 'specializations')['spec'], 'Feral')

    def test_group_search_progress_finishes_after_per_member_errors(self):
        request = ('MPLS2\n123-1\nMPLC1 namesearch\nMPLN1\n'
                   'N\t1\teu\tGordunni\tMissing\tDRUID\tTANK\tknown\n')
        events = []
        def fail(_):
            raise ValueError('HTTP 429')
        # Group search keeps per-client caches, so use a callable object.
        class Client:
            __call__ = staticmethod(fail)
        reply = clipboard_protocol.reply(request, self.mapping, self.cache, Client(), progress=events.append)
        self.assertTrue(reply.startswith('MPLS1\n'), reply)
        self.assertEqual([e['completed'] for e in events], [0, 1])
        self.assertEqual(events[0]['stage'], 'search')

    @unittest.skipUnless(sys.platform == 'win32', 'Windows GUI')
    def test_gui_displays_progress_switches_language_and_clears_stopped_work(self):
        import tkinter as tk
        loader = importlib.machinery.SourceFileLoader('loading_gui_test', str(ROOT / 'tools/companion_gui.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        gui = importlib.util.module_from_spec(spec)
        loader.exec_module(gui)
        with patch.object(gui.local_settings, 'load', return_value={'language': 'ruRU'}), \
             patch.object(gui.windows, 'retail_autostart_enabled', return_value=False), \
             patch.object(gui.windows, 'autostart_enabled', return_value=False), \
             patch.object(gui.windows, 'Tray'), patch.object(sys, 'argv', ['test']):
            root = tk.Tk()
            root.withdraw()
            app = gui.App(root)
            try:
                app.want_running = False
                app.last_heartbeat = time.time()
                app.messages.put(('worker', (app.stop, 'progress', dict(stage='realm_lookup',
                    completed=0, total=14))))
                app.poll()
                self.assertEqual(app.status.get(), 'Определяю серверы персонажей: 0/14')
                self.assertEqual(str(app.progress_bar['mode']), 'determinate')
                self.assertEqual(app.progress_bar['maximum'], 14)
                app.messages.put(('worker', (app.stop, 'progress', dict(stage='realm_lookup',
                    completed=3, total=14))))
                app.poll()
                self.assertEqual(app.progress_bar['value'], 3)
                with patch.object(app, 'save_preferences'):
                    app.language.set('enUS')
                    app.change_language()
                self.assertEqual(app.status.get(), 'Determining character realms: 3/14')
                app.show_progress(dict(stage='search', completed=1, total=4, character='Lumar'))
                self.assertIn('Finding group members: 1/4', app.status.get())
                self.assertEqual(app.progress_bar['maximum'], 4)
                with patch.object(app, 'save_preferences'):
                    app.language.set('ruRU')
                    app.change_language()
                app.messages.put(('worker', (app.stop, 'progress', dict(stage='profiles', completed=2,
                    total=5, character='Киндрих', realm='Гордунни', spec=''))))
                app.poll()
                self.assertIn('Загружаю персонажей: 2/5', app.status.get())
                self.assertEqual(app.progress_bar['value'], 2)
                self.assertEqual(app.progress_bar.winfo_manager(), 'pack')
                with patch.object(app, 'save_preferences'):
                    app.language.set('enUS')
                    app.change_language()
                self.assertIn('Loading characters: 2/5', app.status.get())
                app.messages.put(('worker', (app.stop, 'ready', 'Ответ готов. Буфер изменился — нажмите «Скопировать последний ответ».')))
                app.poll()
                self.assertEqual(app.progress_bar.winfo_manager(), '')
                app.show_progress(dict(stage='preparing'))
                app.messages.put(('worker', (app.stop, 'status', 'HTTP 429')))
                app.poll()
                self.assertEqual(app.progress_bar.winfo_manager(), '')
                app.show_progress(dict(stage='preparing'))
                self.assertEqual(str(app.progress_bar['mode']), 'indeterminate')
                app.stop.set()
                app.messages.put(('worker', (app.stop, 'progress', dict(stage='preparing'))))
                app.poll()
                self.assertEqual(app.progress_bar.winfo_manager(), '')
                stale = threading.Event()
                app.messages.put(('worker', (stale, 'progress', dict(stage='preparing'))))
                app.poll()
                self.assertEqual(app.progress_bar.winfo_manager(), '')
            finally:
                app.exit()
                i18n.set_language('system')


if __name__ == '__main__':
    unittest.main()
