"""Leader hints are negotiated without changing member order or stored identity."""
import unittest
from urllib.parse import unquote

import test_name_search
import clipboard_protocol


class LeaderProbeHintTests(unittest.TestCase):
    def setUp(self):
        test_name_search.NameSearchTests.setUp(self)
        self.lua.globals().MPL=self.mpl
        self.lua.execute('''
            searchMembers[1]={name="Mirkowrr",isLeader=false,classFilename="WARRIOR",assignedRole="DAMAGER"}
            searchMembers[2]={name="Frákkie-Draenor",isLeader=true,classFilename="MONK",assignedRole="DAMAGER"}
            MPL.ShowSearchGroup(10)
        ''')

    def capabilities(self, enabled):
        self.mpl.companionInfo=self.lua.table_from(dict(capabilities=self.lua.table_from(
            dict(namesearch=True, leaderfirst=enabled))))

    def request(self):
        _, request=self.mpl.BeginSearchGroupRequest()
        lines=request.splitlines()
        required=set(lines[2].removeprefix('MPLC1 ').split(','))
        rows=[[unquote(field) for field in line.split('\t')] for line in lines if line.startswith('N\t')]
        return required, rows

    def test_negotiated_leader_hint_preserves_order_and_player_origins(self):
        self.capabilities(True)
        required, rows=self.request()
        self.assertIn('leaderfirst', required)
        self.assertEqual([(row[1],row[4],row[7]) for row in rows],
                         [('1','Mirkowrr','search'),('2','Frákkie','leader')])
        self.assertEqual([len(row) for row in rows],[8,8])
        self.assertEqual(self.mpl.searchGroupWindow.players[2].origin,'known')
        self.assertEqual(self.mpl.searchGroupWindow.requestPlayers[2].origin,'known')
        self.assertTrue(self.mpl.searchGroupWindow.players[2].leader)

    def test_unknown_and_older_companion_get_existing_origins_only(self):
        for known in (False,True):
            if known:
                self.capabilities(False)
            else:
                self.mpl.companionInfo=None
            required, rows=self.request()
            self.assertNotIn('leaderfirst', required)
            self.assertEqual([row[7] for row in rows],['search','known'])
            self.assertEqual([row[4] for row in rows],['Mirkowrr','Frákkie'])

    def test_realm_unknown_leader_has_no_hint(self):
        self.capabilities(True)
        self.lua.execute('leaderName="Frákkie"; searchMembers[2].name="Frákkie"; MPL.searchGroupWindow=nil; MPL.ShowSearchGroup(10)')
        required, rows=self.request()
        self.assertNotIn('leaderfirst',required)
        self.assertEqual(rows[1][3],'')
        self.assertEqual(rows[1][7],'search')

    def test_live_roster_merge_updates_leader_flag(self):
        self.capabilities(True)
        old=self.mpl.searchGroupWindow.players[2]
        self.lua.execute('searchMembers[2].isLeader=false; MPL.UpdateSearchGroupRoster(10)')
        self.assertFalse(self.mpl.searchGroupWindow.players[2].leader)
        self.assertEqual(self.mpl.searchGroupWindow.players[2].name,old.name)
        required, rows=self.request()
        self.assertNotIn('leaderfirst',required)
        self.assertEqual(rows[1][7],'known')

    def test_companion_advertises_negotiated_hint(self):
        self.assertIn('leaderfirst',clipboard_protocol.CAPABILITIES)


if __name__=='__main__':
    unittest.main()
