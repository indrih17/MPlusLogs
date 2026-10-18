"""Cost evidence and negotiated realm rescan use real request boundaries offline."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_addon import ROOT,api_fixture
sys.path.insert(0,str(ROOT/'tools'))
import clipboard_companion as bridge
import clipboard_protocol
import name_search
import realm_resolver
import test_primary_metric


class LoadingOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-loading-')
        self.addCleanup(self.temp.cleanup)
        self.cache=Path(self.temp.name)
        self.client=bridge.Client(token_provider=lambda:'never-save-this-token')
        self.addCleanup(self.client.budget.close)

    def test_request_cost_is_measured_without_character_query_or_credentials(self):
        raw=copy.deepcopy(api_fixture())
        raw['data']['rateLimitData']={'limitPerHour':3600,'pointsSpentThisHour':10,
            'pointsResetIn':500,'currentRequest':{'total':3.25}}
        self.client._query('private-name-in-query',lambda token:raw)
        target=self.cache/'request-metrics.json'
        self.client.save_request_metrics(target)
        saved=target.read_text(encoding='utf-8');record=json.loads(saved)['requests'][0]
        self.assertEqual(record['points'],3.25)
        self.assertEqual(record['kind'],'profile')
        self.assertGreater(record['payloadJsonBytes'],0)
        for private in ('never-save-this-token','private-name-in-query','Киндрих','Гордунни'):
            self.assertNotIn(private,saved)

    def test_missing_or_invalid_cost_is_unknown_never_zero(self):
        for value in (None,{'total':float('nan')},{'total':True},{'total':-1}):
            self.client._record_request({'data':{'rateLimitData':{'currentRequest':value}}},
                bridge.time.monotonic(),False,True)
        self.assertTrue(all(r['points'] is None for r in self.client.request_metrics))

    def test_failed_requests_and_ring_bound_do_not_capture_error_contents(self):
        error=bridge.wcl.APIError('private upstream response',rate_limit={'currentRequest':{'total':2}})
        for _ in range(205):
            self.client._record_request(None,bridge.time.monotonic(),False,True,error)
        self.assertEqual(len(self.client.request_metrics),200)
        self.assertEqual(self.client.request_metrics[-1]['points'],2)
        self.assertEqual(self.client.request_metrics[-1]['outcome'],'error')
        self.assertNotIn('private',json.dumps(self.client.request_metrics))
        with patch.object(bridge.builder,'atomic_write',side_effect=OSError('read only')):
            self.client.save_request_metrics(self.cache/'failed.json')

    def test_rescan_flag_crosses_protocol_and_default_does_not_force_it(self):
        body='MPLQ2\nMPLN1\nN\t1\teu\t\tTest\tWARRIOR\tTANK\tsearch\n'
        mapping=realm_resolver.load_mappings()
        for capabilities,expected in [('namesearch',False),('namesearch,rescan',True)]:
            with patch.object(name_search,'reply',return_value='MPLN2\n') as reply:
                clipboard_protocol.reply('MPLS2\n12345-1\nMPLC1 '+capabilities+'\n'+body,
                                         mapping,self.cache,self.client)
            self.assertEqual(reply.call_args.kwargs['refresh'],expected)

    def test_checkpoint_files_are_disposable_but_metrics_not_arbitrarily_deleted(self):
        import cache_maintenance
        cache=self.cache/'.wcl-cache';cache.mkdir()
        checkpoint=cache/('name-scan-'+'a'*64+'.json');checkpoint.write_text('{}')
        metrics=cache/'request-metrics.json';metrics.write_text('{}')
        cache_maintenance.clean(cache,now=bridge.time.time()+31*86400)
        self.assertFalse(checkpoint.exists())
        self.assertTrue(metrics.exists())

    def test_older_addon_upgrades_partial_cache_and_never_receives_new_record(self):
        body='MPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\tFire\tDAMAGER\n'
        calls=[]
        def fetch(args):
            calls.append(args)
            return test_primary_metric.raw_profile(partial=bridge.wcl.primary_only_request(args))
        mapping=realm_resolver.load_mappings()
        modern='MPLS2\n12345-1\nMPLC1 primarymetric\n'+body
        from urllib.parse import unquote
        reply=unquote(clipboard_protocol.reply(modern,mapping,self.cache,fetch))
        self.assertIn('\nM\tdps\n',reply)
        legacy='MPLS1\n12345-2\n'+body
        reply=unquote(clipboard_protocol.reply(legacy,mapping,self.cache,fetch))
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[-1].include_secondary)
        self.assertNotIn('\nM\tdps\n',reply)

    def test_full_required_does_not_export_partial_fallback_on_network_failure(self):
        body='MPLQ1\nQ\teu\tГордунни\tКиндрих\tdps\tFire\tDAMAGER\n'
        mapping=realm_resolver.load_mappings()
        modern='MPLS2\n12345-1\nMPLC1 primarymetric\n'+body
        clipboard_protocol.reply(modern,mapping,self.cache,lambda args:test_primary_metric.raw_profile(partial=True))
        with patch.object(bridge.wcl,'fetch',side_effect=bridge.wcl.APIError('network unavailable')):
            reply=clipboard_protocol.reply('MPLS1\n12345-2\n'+body,mapping,self.cache,
                lambda args:(_ for _ in ()).throw(bridge.wcl.APIError('network unavailable')))
        self.assertTrue(reply.startswith('MPLE1\n'))
