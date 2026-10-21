"""WCL-shaped table: metric switching preserves identity and honest missing fields."""
import unittest
import test_addon
ROOT=test_addon.ROOT


class ProfileTableTests(unittest.TestCase):
    setUp=test_addon.AddonTests.setUp

    def test_stale_banner_survives_metric_switch_and_popup_setting_then_hides_without_profile(self):
        self.mpl.SetOption("stalePopup",False)
        self.mpl.ShowProfile("Киндрих-Гордунни")
        panel=self.mpl.panel
        self.assertTrue(panel.staleBanner.shown)
        self.assertIn("дата неизвестна",panel.staleBanner.message.text)
        panel.metricTabs.hps.scripts.OnClick()
        self.assertTrue(panel.staleBanner.shown)
        self.assertEqual(panel.height,688)
        self.mpl.ShowProfile("Missing-Silvermoon")
        self.assertFalse(panel.staleBanner.shown)
        self.assertEqual(panel.height,700)

    def test_wcl_column_order_and_snapshot_metadata(self):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        panel=self.mpl.panel
        self.assertEqual([panel.headings[i].text for i in range(1,10)],
                         ["Подземелье","Уровень","Время","Runs","Очки","Ранг","Best DPS","Best %","Median %"])
        row=panel.rows[1]
        self.assertEqual(row.cells[2].text,19)
        self.assertEqual(row.cells[3].text,"29:26")
        self.assertEqual(row.cells[4].text,28)
        self.assertEqual(row.cells[5].text,"470")
        self.assertEqual(row.cells[6].text,1314)
        self.assertEqual(row.cells[7].text,"194.06K")
        self.assertNotIn("%",row.cells[8].text)

    def test_metric_switch_preserves_applicant_and_sent_invitation(self):
        self.mpl.ShowProfile("Киндрих-Гордунни")
        panel=self.mpl.panel
        applicant=self.lua.table_from({"applicantID":123,"name":"Киндрих","realm":"Гордунни"})
        panel.applicant=applicant
        panel.inviteSent=True
        original=panel.profile
        panel.metricTabs.hps.scripts.OnClick()
        self.assertEqual(panel.viewMetric,"hps")
        self.assertEqual(panel.applicant.applicantID,123)
        self.assertTrue(panel.inviteSent)
        self.assertEqual(panel.profile.characterID,original.characterID)
        for column in (2,3,5,6,7,8,9):
            self.assertEqual(panel.rows[1].cells[column].text,"—")
        panel.metricTabs.dps.scripts.OnClick()
        self.assertEqual(panel.rows[1].cells[3].text,"29:26")
        self.assertTrue(panel.inviteSent)

    def test_dungeon_icons_are_real_packaged_textures(self):
        from PIL import Image
        import export_release_source
        textures=list((ROOT / "assets/dungeons").glob("*.tga"))
        self.assertEqual(len(textures),8)
        for path in textures:
            with Image.open(path) as image:
                self.assertEqual(image.size,(32,32))
        entries={entry["path"]:entry for entry in export_release_source.entries()}
        for path in textures:
            self.assertEqual(entries[path.relative_to(ROOT).as_posix()]["encoding"],"base64")


if __name__=="__main__":
    unittest.main()
