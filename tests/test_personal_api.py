"""Personal setup, transactional migration and quota provenance; no live login."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import personal_api
import local_settings
import clipboard_companion as bridge
import realm_resolver
from api_budget import Budget, BudgetError


class PersonalBudgetTests(unittest.TestCase):
    def test_shared_cooldown_does_not_block_personal_client_and_survives_restart(self):
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-work-') as temp:
            root=Path(temp)
            shared_path=personal_api.budget_path(root,'shared','bundled')
            shared=Budget(shared_path,clock=lambda:10000)
            shared.observe({'limitPerHour':700,'pointsSpentThisHour':650,'pointsResetIn':500})
            shared.close()
            shared=Budget(shared_path,clock=lambda:10000)
            own=Budget(personal_api.budget_path(root,'personal','own-client'),clock=lambda:10000)
            try:
                with self.assertRaises(BudgetError): shared.reserve('character')
                self.assertEqual(own.reserve('character'),0)
                self.assertNotEqual(personal_api.budget_path(root,'personal','another-client'),personal_api.budget_path(root,'personal','own-client'))
            finally:
                shared.close(); own.close()

    def test_quota_observation_preserves_actual_reset_and_rejects_invalid_values(self):
        self.assertEqual(personal_api.quota_record({'limitPerHour':700,'pointsSpentThisHour':5,'pointsResetIn':321},10000),
                         {'remaining':695,'limit':700,'reset_at':10321})
        for value in (None, {}, {'limitPerHour':float('nan'),'pointsSpentThisHour':0,'pointsResetIn':60}):
            self.assertIsNone(personal_api.quota_record(value,10000))

    def test_candidate_must_be_own_id_not_example_shared_id_or_url(self):
        self.assertEqual(personal_api.validate_client_id(' own-client-123 ', 'shared'), 'own-client-123')
        for value in ('', personal_api.EXAMPLE_ID, 'shared', 'https://wcl.example/client', 'a b'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                personal_api.validate_client_id(value, 'shared')

    def test_reply_carries_the_selected_clients_actual_reset(self):
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-work-') as temp:
            for mode, reset in [('shared',610),('personal',123)]:
                client=bridge.Client(token_provider=lambda:'unused')
                client.api_mode=mode
                client.budget.clock=lambda:10000
                client.budget.observe({'limitPerHour':700,'pointsSpentThisHour':650,'pointsResetIn':reset})
                try:
                    request='MPLQ2\nQ\teu\tГордунни\tКиндрих\tdps\tGuardian\n'
                    with patch.object(bridge.wcl,'fetch') as fetch:
                        reply,report=bridge.process_request(request,realm_resolver.load_mappings(),Path(temp)/mode,client)
                    fetch.assert_not_called()
                    self.assertIn('API reset at '+str(10000+reset),report['errors'][0]['error'])
                    self.assertIn(mode.title()+' API; ',report['errors'][0]['error'])
                    self.assertIn('F\t',reply)
                finally:
                    client.budget.close()


@unittest.skipUnless(sys.platform=='win32','Windows UI and DPAPI')
class PersonalSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader=importlib.machinery.SourceFileLoader('personal_api_gui_test',str(ROOT/'tools/companion_gui.pyw'))
        cls.gui=importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,loader))
        loader.exec_module(cls.gui)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-work-')
        self.addCleanup(self.temp.cleanup)
        self.shared=json.loads((ROOT/'tools/oauth_client.json').read_text())['client_id']
        self.old={'oauth_client_id':self.shared, 'language':'enUS',
                  'oauth':{'access_token':'old-test-token','expires_at':time.time()+3600}}
        for target,name,kwargs in (
            (local_settings,'load',{'return_value':dict(self.old)}),
            (local_settings,'PATH',{'new':Path(self.temp.name)/'settings.json'}),
            (self.gui.windows,'Tray',{'return_value':None}),
            (self.gui.windows,'retail_autostart_enabled',{'return_value':False}),
            (self.gui.windows,'autostart_enabled',{'return_value':False}),
            (sys,'argv',{'new':['test']}),
        ):
            p=patch.object(target,name,**kwargs); p.start(); self.addCleanup(p.stop)
        self.root=tk.Tk(); self.root.withdraw()
        self.app=self.gui.App(self.root)
        self.app.last_heartbeat=time.time()
        p=patch.object(self.app,'start'); p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.app.exit)

    def test_guide_fields_remain_readable_and_canvas_matches_both_themes(self):
        self.app.show_personal_setup()
        wizard=self.app.personal_setup
        def luminance(color):
            values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            values=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in values]
            return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
        for mode in ('dark','light'):
            self.app.theme.set(mode); self.app.refresh_theme()
            self.assertEqual(wizard.canvas.cget('background'),self.root.cget('background'))
            style=ttk.Style(self.root)
            fg=style.lookup('TEntry','foreground',('readonly',))
            bg=style.lookup('TEntry','fieldbackground',('readonly',))
            a,b=sorted((luminance(fg),luminance(bg)))
            self.assertGreaterEqual((b+.05)/(a+.05),4.5)
        wizard.scroll_state('0','1')
        self.assertEqual(wizard.scrollbar.winfo_manager(),'')
        wizard.scroll_state('0','.5')
        self.assertEqual(wizard.scrollbar.winfo_manager(),'pack')

    def test_existing_shared_login_can_open_all_steps_and_copy_exact_callback(self):
        self.assertEqual(self.app.api_title.get(),'Shared API connected')
        self.assertEqual(self.app.personal_button_text.get(),'Switch to personal API')
        self.app.show_personal_setup()
        wizard=self.app.personal_setup
        self.assertEqual(wizard.progress.get(),'Step 1 of 3')
        wizard.advance()
        self.assertEqual(wizard.progress.get(),'Step 2 of 3')
        self.assertEqual(wizard.images['personal-api-form.png'].width(),680)
        wizard.copy(self.gui.wcl_oauth.REDIRECT_URI)
        self.assertEqual(self.root.clipboard_get(),'http://127.0.0.1:43827/callback')
        wizard.advance()
        wizard.paste()
        self.assertEqual(wizard.client_id.get(),self.gui.wcl_oauth.REDIRECT_URI)
        wizard.client_id.set(personal_api.EXAMPLE_ID)
        wizard.advance()
        self.assertFalse(wizard.pending)
        self.assertIsNone(self.app.auth_worker)
        with patch.object(self.app,'save_preferences'):
            self.app.language.set('ruRU'); self.app.change_language()
        self.assertEqual(wizard.progress.get(),'Шаг 3 из 3')

    def test_successful_personal_login_persists_own_client_and_protected_tokens(self):
        tokens={'access_token':'new-test-token','expires_at':time.time()+3600}
        with patch.object(self.gui.wcl_oauth,'login',return_value=tokens) as login, \
             patch.object(self.gui.wcl_oauth,'validate_access',return_value={'limitPerHour':700,'pointsSpentThisHour':50,'pointsResetIn':555}):
            self.app.show_personal_setup(); wizard=self.app.personal_setup
            wizard.show(2); wizard.client_id.set('own-client-123'); wizard.advance()
            self.app.auth_worker.join(3)
            self.app.poll()
        self.assertEqual(login.call_args.args[0],'own-client-123')
        self.assertEqual(self.app.api_mode,'personal')
        self.assertEqual(self.app.session.client_id,'own-client-123')
        self.assertIsNone(self.app.personal_setup)
        self.assertIn('650',self.app.api_quota.get())
        disk=json.loads(local_settings.PATH.read_text())
        self.assertEqual(disk['personal_client_id'],'own-client-123')
        self.assertEqual(disk['api_mode'],'personal')
        self.assertIn('oauth_dpapi',disk)
        self.assertNotIn('new-test-token',local_settings.PATH.read_text())

    def test_failure_cancel_and_save_failure_preserve_previous_connection(self):
        old_session=self.app.session
        for failure in ('auth','save','cancel'):
            with self.subTest(failure=failure):
                self.app.show_personal_setup(); wizard=self.app.personal_setup
                wizard.show(2); wizard.client_id.set('own-client-123')
                if failure=='cancel':
                    wizard.pending=True; self.app.want_running=False
                    wizard.close()
                elif failure=='auth':
                    with patch.object(self.gui.wcl_oauth,'login',side_effect=ValueError('test denied')):
                        wizard.advance(); self.app.auth_worker.join(3); self.app.poll()
                    self.assertFalse(wizard.pending); wizard.close()
                else:
                    wizard.pending=True
                    self.app.auth_cancel=threading.Event()
                    self.app.messages.put(('configured_auth',({'access_token':'fake'},self.app.auth_cancel,'own-client-123','personal','')))
                    with patch.object(local_settings,'save_config',side_effect=OSError('test save failed')):
                        self.app.poll()
                    self.assertFalse(wizard.pending); wizard.close()
                self.assertIs(self.app.session,old_session)
                self.assertEqual(self.app.client_id,self.shared)
                self.assertEqual(self.app.api_mode,'shared')
                self.assertTrue(self.app.want_running)


if __name__=='__main__': unittest.main()
