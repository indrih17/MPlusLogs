"""Optional metric upgrades cross actual client admission and batch import boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_batch
import test_primary_metric
import build_database as builder
import clipboard_companion as bridge
import clipboard_protocol
import realm_resolver
import wcl_sync as wcl


class MetricBudgetUpgradeTests(unittest.TestCase):
    def test_immediate_primary_to_full_upgrade_reserves_once_each_but_repeated_full_cools(self):
        temp=tempfile.TemporaryDirectory(dir=test_batch.ROOT,prefix='.test-budget-upgrade-')
        self.addCleanup(temp.cleanup)
        folder=temp.name
        cache=Path(folder)
        client=bridge.Client(token_provider=lambda:'offline-test-token',state_path=cache/'budget.sqlite3')
        self.addCleanup(client.budget.close)
        entry=dict(name='Киндрих',realm='Гордунни',server_slug='gordunni',region='eu',
                   role='DAMAGER',class_id=8,allow_primary=True)
        calls=[]
        def fetch(args,token,endpoint):
            calls.append(copy.copy(args))
            raw=test_primary_metric.raw_profile(partial=wcl.primary_only_request(args))
            raw['data']['rateLimitData']=dict(limitPerHour=3600,pointsSpentThisHour=10+2*len(calls),
                pointsResetIn=3600,currentRequest=dict(total=2))
            return raw
        with patch.object(wcl,'fetch',side_effect=fetch):
            first,report=builder.build([entry],cache,fetcher=client)
            self.assertEqual(len(first),1)
            self.assertEqual(report['fetched'],1)
            self.assertTrue(wcl.primary_only_request(calls[0]))
            full_entry=dict(entry,metric='hps')
            second,report=builder.build([full_entry],cache,fetcher=client)
            self.assertEqual(len(second),1,report['errors'])
            self.assertEqual(report['fetched'],1)
            self.assertFalse(wcl.primary_only_request(calls[-1]))
            self.assertNotIn(wcl.PRIMARY_ONLY_MARKER,
                builder.read_cache(builder.cache_path(cache,entry))['raw'])
            self.assertEqual(len(calls),2)
            with self.assertRaisesRegex(ValueError,'cooling down'):
                client(builder.arguments(full_entry))
        self.assertEqual(client.queries,2)
        self.assertEqual(client.budget.snapshot()['counters']['upstream_attempts'],2)

class PrimaryBatchRoundtripTests(unittest.TestCase):
    setUp=test_batch.BatchTests.setUp

    def test_negotiated_primary_profile_keeps_damager_role_through_real_batch_import(self):
        self.lua.execute("""
            local MPL=...
            MPL.companionInfo={version='1.0.20',capabilities={primarymetric=true,lazyspecs=true}}
        """,self.mpl)
        players=self.lua.table_from([self.lua.table_from(dict(name='Bob',realm='Гордунни',
            region='eu',role='DAMAGER',spec='Fire'))])
        _,request=self.mpl.SendBatchRequest(players)
        self.assertIn('primarymetric',request)
        calls=[]
        def fetch(args):
            calls.append(args)
            raw=test_primary_metric.raw_profile(partial=wcl.primary_only_request(args))
            raw['data']['characterData']['character']['name']='Bob'
            return raw
        reply=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,fetch)
        self.assertEqual(len(calls),1)
        self.assertTrue(wcl.primary_only_request(calls[0]))
        result=self.mpl.ReceiveReply(reply,True)
        self.assertEqual(result,1)
        profile,_,_=self.mpl.GetProfile('Bob','Гордунни','Fire','DAMAGER')
        self.assertEqual(self.mpl.ProfileRole(profile),'DAMAGER')
        self.assertEqual(profile.metric,'dps')
        self.assertTrue(profile.secondaryPending)
        self.assertIsNone(self.mpl.pendingReply)


if __name__=='__main__':unittest.main()
