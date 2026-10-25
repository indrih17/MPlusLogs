"""Validated GUI re-login releases auth gates while preserving quota and other errors."""
import importlib.machinery
import importlib.util
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

from test_addon import ROOT,api_fixture
sys.path.insert(0,str(ROOT/'tools'))
import api_budget
import build_database as builder
import clipboard_companion as bridge
import personal_api
import wcl_oauth as oauth
import wcl_sync as wcl

loader=importlib.machinery.SourceFileLoader('auth_generation_gui',str(ROOT/'tools/companion_gui.pyw'))
spec=importlib.util.spec_from_loader(loader.name,loader)
gui=importlib.util.module_from_spec(spec)
loader.exec_module(gui)


class AuthGenerationFlowTests(unittest.TestCase):
    def tokens(self):
        tokens=dict(access_token='offline-fixture',refresh_token='offline-refresh',expires_at=time.time()+3600)
        probe={'data':{'characterData':{'__typename':'CharacterData'},'userData':{'currentUser':{'id':17}}}}
        with patch.object(wcl,'request_json',return_value=probe):oauth.validate_access(tokens)
        return tokens

    def app(self,tokens):
        app=gui.App.__new__(gui.App)
        app.config_lock=threading.RLock()
        app.config=dict(oauth=tokens,oauth_client_id='public-id',personal_client_id='public-id',api_mode='personal')
        app.client_id='public-id';app.api_mode='personal'
        app.session=app.make_session(tokens)
        app.auth_cancel=threading.Event()
        app.messages=queue.Queue()
        app.stop=threading.Event()
        app.exiting=app.installing_update=False
        app.instance=app.personal_setup=None
        app.last_theme_check=time.monotonic();app.last_heartbeat=time.time()
        app.root=Mock();app.root.winfo_height.return_value=330
        app.body=Mock();app.body.winfo_reqheight.return_value=330
        app.start=Mock();app.clear_progress=Mock();app.refresh_api_display=Mock()
        app.account=Mock();app.login_button=Mock();app.status=Mock()
        return app

    def test_same_account_configured_auth_releases_only_auth_owned_gates(self):
        for blocker in ('auth-only','quota','other-error'):
            with self.subTest(blocker=blocker),tempfile.TemporaryDirectory(prefix='.test-work-auth-',dir=ROOT) as temp:
                directory=Path(temp)
                app=self.app(self.tokens())
                old_scope=app.session.cache_scope()
                old_generation=app.session.auth_generation()
                state=personal_api.budget_path(directory,app.api_mode,app.client_id)
                real_client=bridge.Client
                old=real_client(3600,token_provider=app.session.access_token,invalidate_token=app.session.invalidate,
                                state_path=state,cache_scope=old_scope,auth_generation=old_generation)
                created=[]
                try:
                    old.budget.observe(dict(limitPerHour=36000,pointsSpentThisHour=10,pointsResetIn=600))
                    args=builder.arguments(dict(name='One',realm='Gordunni',region='eu',server_slug='gordunni',spec=''))
                    with patch.object(wcl,'fetch',side_effect=wcl.APIError('WCL HTTP 401',status=401,code='auth')):
                        with self.assertRaises(wcl.APIError):old(args)
                    if blocker=='quota':
                        old.budget.observe(dict(limitPerHour=36000,pointsSpentThisHour=35999,pointsResetIn=600))
                    elif blocker=='other-error':
                        old.budget.failure(wcl.APIError('WCL GraphQL query failed',code='schema'))
                    spent=old.budget.snapshot()['pointsSpentThisHour']
                    new_tokens=self.tokens()
                    app.messages.put(('configured_auth',(new_tokens,app.auth_cancel,app.client_id,app.api_mode)))
                    with patch.object(gui.local_settings,'save_config') as save:app.poll()
                    self.assertEqual(save.call_args.args[0]['oauth']['_auth_generation'],app.session.auth_generation())
                    self.assertNotEqual(app.session.auth_generation(),old_generation)
                    self.assertEqual(app.session.cache_scope(),old_scope)
                    def make_client(*args,**kwargs):
                        client=real_client(*args,**kwargs);created.append(client);return client
                    stop=Mock();stop.wait.return_value=True;stop.is_set.return_value=False
                    with patch.object(gui,'DATA_ROOT',directory),patch.object(gui.bridge,'WindowsClipboard'), \
                         patch.object(gui.realm_resolver,'load_mappings',return_value={}), \
                         patch.object(gui.bridge,'Client',side_effect=make_client):
                        app.watch(stop,app.session,False,0)
                    self.assertEqual(len(created),1)
                    current=created[0]
                    self.assertEqual(current.auth_generation,app.session.auth_generation())
                    self.assertEqual(current.budget.snapshot()['pointsSpentThisHour'],spent)
                    raw=api_fixture();raw['data']['characterData']['character']['name']='One'
                    with patch.object(wcl,'fetch',return_value=raw) as fetch:
                        if blocker=='auth-only':
                            current(args)
                            fetch.assert_called_once()
                        else:
                            with self.assertRaises(api_budget.BudgetError) as failure:current(args)
                            self.assertEqual(failure.exception.code,'budget' if blocker=='quota' else 'retry')
                            fetch.assert_not_called()
                finally:
                    for client in created:client.budget.close()
                    old.budget.close()


if __name__=='__main__':unittest.main()
