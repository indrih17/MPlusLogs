"""Lazy spec discovery preserves choices without fetching every spec."""
from pathlib import Path
import tempfile
import unittest

import test_addon
import clipboard_protocol
import realm_resolver


class QuotaOptimizationTests(unittest.TestCase):
    setUp = test_addon.AddonTests.setUp

    def raw(self, args):
        raw = test_addon.api_fixture()
        performance = raw['data']['characterData']['character']['performance']
        performance['allStars'] = [{'spec': spec, 'points': 3774} for spec in
                                   ([args.spec] if args.spec else ['Guardian', 'Feral'])]
        performance['rankings'][0]['bestSpec'] = args.spec or 'Guardian'
        return raw

    def test_one_request_discovers_specs_and_targeted_load_fetches_only_selection(self):
        self.lua.execute('return assert(loadstring(...))',
                         (test_addon.ROOT/'Transport.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)
        self.lua.execute('C_Timer={After=function() end}')
        self.mpl.companionInfo=self.lua.table_from({'capabilities':{'lazyspecs':True}},recursive=True)
        calls = []
        def fetch(args):
            calls.append(args.spec)
            return self.raw(args)
        with tempfile.TemporaryDirectory(dir=test_addon.ROOT,prefix='.test-work-') as folder:
            cache = Path(folder)
            _, request = self.mpl.SendRequest('Киндрих','Гордунни','dps','All specs',None,True)
            reply = clipboard_protocol.reply(request,realm_resolver.load_mappings(),cache,fetch)
            self.assertEqual(self.mpl.ReceiveReply(reply,True),(1,None))
            self.assertEqual(calls,[None])
            self.assertEqual(set(self.mpl.ProfileSpecs('Киндрих','Гордунни').values()),{'Guardian','Feral'})
            self.assertIsNone(self.mpl.GetProfile('Киндрих','Гордунни','Feral')[0])
            self.lua.execute('''
                MenuUtil={CreateContextMenu=function(_,build)
                    specRadios={}
                    build(nil,{CreateTitle=function() end,CreateDivider=function() end,CreateButton=function() end,
                        CreateRadio=function(_,text,selected,callback) specRadios[#specRadios+1]=callback end})
                end}
            ''')
            self.mpl.panel.specButton.scripts.OnClick()
            self.lua.globals().specRadios[2]()  # All specs, Feral, Guardian.
            self.assertEqual(self.mpl.pendingReply.spec,'Feral')
            self.assertFalse(self.mpl.pendingReply.batch)
            request = self.mpl.downloadWindow.request
            reply = clipboard_protocol.reply(request,realm_resolver.load_mappings(),cache,fetch)
            self.assertEqual(self.mpl.ReceiveReply(reply,True),(1,None))
            self.assertEqual(calls,[None,'Feral'])
            self.assertIsNotNone(self.mpl.GetProfile('Киндрих','Гордунни','Feral')[0])
            # The same fresh profile is served without another upstream call.
            _, request = self.mpl.SendRequest('Киндрих','Гордунни','dps','Feral',None,True)
            self.mpl.ReceiveReply(clipboard_protocol.reply(request,realm_resolver.load_mappings(),cache,fetch),True)
            self.assertEqual(calls,[None,'Feral'])


if __name__ == '__main__':
    unittest.main()
