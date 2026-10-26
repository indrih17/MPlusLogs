"""Selected log specialization remains visible independently of live spec.

Exercises StoreProfiles/SelectSpec/ShowProfile with production layout. Frame
geometry mocks do not establish actual game glyph or texture rendering.
"""
import unittest

import test_profile_appearance as appearance


class SelectedSpecDisplayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = appearance.ProfileAppearanceTests(methodName='runTest')
        self.fixture.setUp()
        self.lua, self.mpl, self.panel = self.fixture.lua, self.fixture.mpl, self.fixture.panel
        self.lua.execute('''
            local MPL,panel=...
            local function clone(value)
                if type(value)~="table" then return value end
                local result={}; for k,v in pairs(value) do result[k]=clone(v) end
                return result
            end
            local aggregate=clone(panel.profile)
            aggregate.spec="All specs"; aggregate.primarySpec="Feral"; aggregate.role="DAMAGER"
            local alternate=clone(aggregate)
            alternate.spec="Balance"; alternate.best=87
            MPL.StoreProfiles({aggregate,alternate})
            MPL.RecordApplicant("Киндрих-Гордунни","DAMAGER",103,"DRUID")
        ''', self.mpl, self.panel)
        self.show('All specs')
        self.current_name = self.panel.currentSpec.name.text

    def show(self, spec):
        self.mpl.SelectSpec('Киндрих', 'Гордунни', spec, 'DAMAGER')
        self.fixture.show_profile('Киндрих', 'Гордунни', None, True)

    @staticmethod
    def top(field):
        return -field.points.TOPLEFT[2]

    def test_selected_alternate_is_visible_below_actual_spec_in_modern_header(self):
        self.show('Balance')
        panel = self.panel
        self.assertEqual(panel.selectedSpec, 'Balance')
        self.assertEqual(panel.profile.spec, 'Balance')
        self.assertEqual(panel.currentSpec.name.text, self.current_name)
        log_spec = panel.logSpec
        self.assertIsNotNone(log_spec)
        self.assertTrue(log_spec.shown)
        self.assertEqual(log_spec.text, self.mpl.L['Logs: '] + self.mpl.SpecLabel('Balance', 'DRUID'))
        name_bottom = self.top(panel.currentSpec.name) + panel.currentSpec.name.height
        self.assertGreaterEqual(self.top(log_spec), name_bottom)
        self.assertGreaterEqual(panel.currentSpec.height, self.top(log_spec) + log_spec.height)
        absolute_bottom = self.top(panel.currentSpec) + panel.currentSpec.height
        self.assertGreaterEqual(self.top(panel.headerViewport), absolute_bottom + 6)

    def test_missing_selected_logs_show_explicit_not_loaded_context(self):
        self.show('Restoration')
        panel = self.panel
        self.assertEqual(panel.selectedSpec, 'Restoration')
        self.assertFalse(panel.profile)
        self.assertEqual(panel.currentSpec.name.text, self.current_name)
        self.assertIsNotNone(panel.logSpec)
        self.assertTrue(panel.logSpec.shown)
        self.assertEqual(panel.logSpec.text,
                         self.mpl.L['Logs: '] + self.mpl.SpecLabel('Restoration', 'DRUID') + self.mpl.L[' — not loaded'])

    def test_all_specs_clears_secondary_context_and_original_keeps_real_selector(self):
        self.show('Balance')
        self.assertIsNotNone(self.panel.logSpec)
        self.assertTrue(self.panel.logSpec.shown)
        self.show('All specs')
        self.assertFalse(self.panel.logSpec.shown)
        self.assertEqual(self.panel.currentSpec.name.text, self.current_name)
        self.show('Balance')
        self.fixture.set('headerLayout', 'original')
        self.assertFalse(self.panel.logSpec.shown)
        self.assertTrue(self.panel.specButton.shown)
        self.assertEqual(self.panel.specButton.text, self.mpl.SpecLabel('Balance', 'DRUID'))
        self.fixture.set('headerLayout', 'modern')
        self.assertTrue(self.panel.logSpec.shown)

    def test_selected_context_wraps_without_covering_table_or_identity_controls(self):
        self.show('Balance')
        self.assertIsNotNone(self.panel.logSpec)
        self.lua.globals().UIParent.SetSize(self.lua.globals().UIParent,700,1080)
        self.fixture.set('size_secondary',30)
        panel = self.panel
        self.assertTrue(panel.logSpec.shown)
        self.assertTrue(panel.logSpec.wordWrap)
        self.assertLessEqual(panel.logSpec.points.TOPLEFT[1] + panel.logSpec.width, panel.currentSpec.width)
        self.assertGreaterEqual(panel.currentSpec.height, self.top(panel.logSpec) + panel.logSpec.height)
        table_top = self.top(panel.headerViewport)
        self.assertGreaterEqual(table_top, self.top(panel.currentSpec) + panel.currentSpec.height + 6)
        before = (panel.height, panel.currentSpec.height, panel.logSpec.height, table_top)
        self.mpl.RenderProfileStats(panel)
        self.assertEqual((panel.height,panel.currentSpec.height,panel.logSpec.height,self.top(panel.headerViewport)), before)


if __name__ == '__main__':
    unittest.main()
