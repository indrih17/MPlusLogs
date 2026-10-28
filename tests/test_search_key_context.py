"""Listing key ranges reach name search without reusing another range's identity."""
import unittest
from unittest.mock import patch
import test_name_search
import test_name_search_roles


class SearchKeyContextTests(unittest.TestCase):
    def setUp(self):
        test_name_search.NameSearchTests.setUp(self)
        self.lua.execute('''
            listingTitle="KR +18"
            listingMythic=true
            C_LFGList.GetActivityInfoTable=function() return {isMythicPlusActivity=listingMythic} end
            C_LFGList.GetSearchResultInfo=function()
                return {name=listingTitle,leaderName=leaderName,activityIDs={1},numMembers=#searchMembers}
            end
        ''')

    def collect(self,title):
        self.lua.globals().listingTitle=title
        return self.mpl.CollectSearchGroup(10)

    def test_title_key_levels_and_ranges(self):
        for title,expected in (('18',(18,18)),('+18',(18,18)),('KR +18 weekly',(18,18)),
                               ('18-19',(18,19)),('KR +18-19',(18,19)),('KR +18 - +19',(18,19)),
                               ('S2 KR +18 ilvl 328',(18,18)),('|cffffffff+18|r',(18,18)),
                               ('+18+++',(18,18))):
            with self.subTest(title=title):
                players,_=self.collect(title)
                self.assertEqual((players[2].keyMin,players[2].keyMax),expected)

    def test_legacy_activity_id_still_transports_listing_level(self):
        self.lua.execute('''
            C_LFGList.GetSearchResultInfo=function()
                return {name="+18",leaderName=leaderName,activityID=1,numMembers=#searchMembers}
            end
        ''')
        players,_=self.mpl.CollectSearchGroup(10)
        self.assertEqual((players[2].keyMin,players[2].keyMax),(18,18))

    def test_mythic_keystone_difficulty_identifies_activity(self):
        self.lua.execute('C_LFGList.GetActivityInfoTable=function() return {difficultyID=8} end')
        players,_=self.collect('+18')
        self.assertEqual((players[2].keyMin,players[2].keyMax),(18,18))

    def test_incidental_or_ambiguous_numbers_are_not_key_context(self):
        for title in ('S2','ilvl 18','itemlevel 18','rating 18','rio 18','328','90','18:00',
                      '18.5','KR +18 +20','19-18','+0','+101','KR 18/19','KR18'):
            with self.subTest(title=title):
                players,_=self.collect(title)
                self.assertIsNone(players[2].keyMin)

    def test_non_mythic_and_secret_titles_are_ignored(self):
        self.lua.globals().listingMythic=False
        players,_=self.collect('+18')
        self.assertIsNone(players[2].keyMin)
        self.lua.execute('listingMythic=true; issecretvalue=function(value) return value==listingTitle end')
        players,_=self.collect('+18')
        self.assertIsNone(players[2].keyMin)

    def test_envelope_transports_key_range_and_requests_capability(self):
        self.mpl.ShowSearchGroup(10)
        self.mpl.BeginSearchGroupRequest()
        request=self.mpl.searchGroupWindow.request
        self.assertIn(',keycontext',request)
        rows=[row.split('\t') for row in request.splitlines() if row.startswith('N\t')]
        self.assertEqual([row[9:11] for row in rows],[['18','18'],['18','18']])
        self.assertTrue(all(len(row)==11 for row in rows))

    def test_context_transport_without_character_level_keeps_empty_column(self):
        self.lua.execute('GetMaxLevelForPlayerExpansion=nil')
        self.mpl.ShowSearchGroup(10)
        self.mpl.BeginSearchGroupRequest()
        rows=[row.split('\t') for row in self.mpl.searchGroupWindow.request.splitlines() if row.startswith('N\t')]
        self.assertEqual(rows[0][8:11],['','18','18'])

    def test_no_key_context_preserves_old_request_shape(self):
        self.lua.globals().listingTitle='Weekly run'
        self.mpl.ShowSearchGroup(10)
        self.mpl.BeginSearchGroupRequest()
        request=self.mpl.searchGroupWindow.request
        self.assertNotIn('keycontext',request)
        rows=[row.split('\t') for row in request.splitlines() if row.startswith('N\t')]
        self.assertTrue(all(len(row) in (8,9) for row in rows))

    def test_new_context_discards_inferred_realm_and_keeps_explicit_realm(self):
        self.mpl.ShowSearchGroup(10)
        players=self.mpl.searchGroupWindow.players
        players[2].realm='Silvermoon'
        players[2].loaded=True
        before=self.mpl.searchGroupWindow.signature
        self.lua.globals().listingTitle='KR +20'
        self.mpl.UpdateSearchGroupRoster(10)
        after=self.mpl.searchGroupWindow
        self.assertNotEqual(after.signature,before)
        self.assertIsNone(after.players[2].realm)
        self.assertEqual(after.players[1].realm,'Draenor')
        self.assertEqual(after.players[1].keyMin,20)

    def test_session_roster_cache_is_scoped_to_key_context(self):
        self.mpl.ShowSearchGroup(10)
        player=self.mpl.searchGroupWindow.players[2]
        player.realm='Silvermoon'; player.loaded=True
        self.mpl.ShowSearchGroup(11)
        self.assertEqual(self.mpl.searchGroupWindow.players[2].realm,'Silvermoon')
        self.lua.globals().listingTitle='KR +20'
        self.mpl.ShowSearchGroup(12)
        self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)

    def test_listing_context_selects_realms_through_full_clipboard_exchange(self):
        self.lua.execute('''
            searchMembers[2].name="Stormek"
            searchMembers[2].classFilename="SHAMAN"
            searchMembers[2].assignedRole="HEALER"
        ''')
        shamans=test_name_search_roles.NameSearchRoleTests().shaman_client(
            {'silvermoon':(3651,0),'tarren-mill':(1457,2425)},
            {'silvermoon':18,'tarren-mill':21})
        leader=test_name_search.Client()
        def client(args):
            return shamans(args) if args.name=='Stormek' else leader(args)
        client.name_search=shamans.name_search
        for level,realm in ((18,'Silvermoon'),(20,'Tarren-Mill')):
            with self.subTest(level=level):
                self.lua.globals().listingTitle='KR +'+str(level)
                self.mpl.ShowSearchGroup(10)
                self.assertIsNone(self.mpl.searchGroupWindow.players[2].realm)
                self.mpl.BeginSearchGroupRequest()
                reply=test_name_search.clipboard_protocol.reply(
                    self.mpl.searchGroupWindow.request,test_name_search.realm_resolver.load_mappings(),
                    self.cache,client)
                self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2 if level==18 else 1)
                self.assertEqual(self.mpl.searchGroupWindow.players[2].realm,realm)

    def test_old_companion_rejects_key_context_before_fetching_characters(self):
        self.mpl.ShowSearchGroup(10)
        self.mpl.BeginSearchGroupRequest()
        client=test_name_search.Client()
        protocol=test_name_search.clipboard_protocol
        with patch.object(protocol,'CAPABILITIES',protocol.CAPABILITIES-{'keycontext'}):
            reply=protocol.reply(self.mpl.searchGroupWindow.request,
                                 test_name_search.realm_resolver.load_mappings(),self.cache,client)
        count,error=self.mpl.ReceiveSearchGroupReply(reply)
        self.assertIsNone(count)
        self.assertIn('Companion',error)
        self.assertEqual(client.calls,[])

    def test_twenty_title_excludes_public_empty_season_through_clipboard(self):
        self.lua.globals().listingTitle='+20'
        empty=test_name_search_roles.NameSearchRoleTests().empty_season_client()
        leader=test_name_search.Client()
        def client(args):
            return empty(args) if args.name=='Mirkowrr' else leader(args)
        client.name_search=empty.name_search
        self.mpl.ShowSearchGroup(10)
        self.mpl.BeginSearchGroupRequest()
        request=self.mpl.searchGroupWindow.request
        rows=[row.split('\t') for row in request.splitlines() if row.startswith('N\t')]
        self.assertEqual(rows[1][9:11],['20','20'])
        reply=test_name_search.clipboard_protocol.reply(request,
            test_name_search.realm_resolver.load_mappings(),self.cache,client)
        self.assertEqual(self.mpl.ReceiveSearchGroupReply(reply),2)
        player=self.mpl.searchGroupWindow.players[2]
        self.assertEqual(player.realm,'Silvermoon')
        self.assertTrue(player.loaded)
        self.assertIsNone(player.candidates)


if __name__=='__main__': unittest.main()
