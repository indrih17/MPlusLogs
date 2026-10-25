"""Notification counts come from completed protocol records, never request size."""
import sys
import unittest
from urllib.parse import quote

from test_addon import ROOT
sys.path.insert(0,str(ROOT/'tools'))
import clipboard_protocol as protocol
import wcl_sync as wcl


def profile(name='One',spec='All specs',source='WCL API'):
    return wcl.line('P','eu','Realm',name,'55','Season',spec,'dps',1,50,40,2,'2026-10-25 10:00 UTC',source,12,'realm')+'\nE\n'


def envelope(body,metadata=True):
    return 'MPLS1\n123-1\n'+('MPLV1 1.0.30 batch,errorcodes\n' if metadata else '')+'MPLB1\n'+quote(body,safe='\n')


class ReplySummaryTests(unittest.TestCase):
    def test_failure_only_batch_reports_no_profiles(self):
        body='MPL2\n'+''.join(wcl.line('F','eu','Realm','Player'+str(i),'MPLERR1 schema 1234:WCL error')+'\n' for i in range(22))
        self.assertEqual(protocol.reply_summary(envelope(body)),dict(available=0,failed=22,unavailable=22,cached=0,choices=0))

    def test_partial_batch_counts_cached_fallback_separately(self):
        body='MPL2\n'+profile()+profile('Two',source='WCL API: cached; refresh unavailable')
        body+=wcl.line('F','eu','Realm','Two','refresh failed')+'\n'+wcl.line('F','eu','Realm','Three','unavailable')+'\n'
        self.assertEqual(protocol.reply_summary(envelope(body)),dict(available=2,failed=2,unavailable=1,cached=1,choices=0))

    def test_specializations_do_not_inflate_character_count(self):
        body='MPL2\n'+profile(spec='Guardian')+profile(spec='Restoration')
        self.assertEqual(protocol.reply_summary(envelope(body))['available'],1)

    def test_duplicate_profile_variant_never_reports_success(self):
        for duplicate in (profile(),profile(source='WCL API: cached; refresh unavailable')):
            with self.subTest(duplicate=duplicate):
                self.assertIsNone(protocol.reply_summary(envelope('MPL2\n'+profile()+duplicate)))
        body='MPL2\n'+profile()+profile().replace('\tdps\t','\thps\t')
        self.assertEqual(protocol.reply_summary(envelope(body))['available'],1)

    def test_invalid_eighteen_field_profile_header_is_not_counted(self):
        invalid=profile().replace('\nE\n','\tDAMAGER\t50\nE\n')
        self.assertIsNone(protocol.reply_summary(envelope('MPL2\n'+invalid)))

    def test_legacy_and_crlf_replies_remain_countable(self):
        body='MPL1\n'+profile('Mignøn')
        self.assertEqual(protocol.reply_summary(envelope(body,False).replace('\n','\r\n'))['available'],1)
        self.assertEqual(protocol.reply_summary('MPLS1\n123-1\n'+body)['available'],1)

    def test_name_search_counts_members_and_unresolved_choices(self):
        body='MPLN2\n'+wcl.line('P',1,'eu','Realm','One','DRUID','MPL1\n'+profile())+'\n'
        body+=wcl.line('C',2,'eu','A','Two','MAGE')+'\n'+wcl.line('C',2,'eu','B','Two','MAGE')+'\n'
        body+=wcl.line('F',3,'MPLERR1 retry 100:retry')+'\n'
        self.assertEqual(protocol.reply_summary(envelope(body)),dict(available=1,failed=1,unavailable=1,cached=0,choices=1))

    def test_unrecognized_or_incomplete_payload_has_no_success_count(self):
        for value in ('private text','MPLE1\n123-1\nerror',envelope('MPL2\n'+profile().removesuffix('E\n')),
                      envelope('MPL2\nP\teu\tRealm\tOne\nE\n'),envelope('MPL2\nwat\n'),
                      'MPLS1\n123-1\nMPLB1\nMPL2\nF%09eu%09Realm%09One%09%XX',
                      'MPLS1\n123-1\nMPLB1\n'+('x'*1500001)):
            with self.subTest(value=value[:80]):self.assertIsNone(protocol.reply_summary(value))


if __name__=='__main__':unittest.main()
