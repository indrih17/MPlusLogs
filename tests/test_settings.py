"""Native settings registration and live display/cache preferences."""
import unittest
import test_batch
import test_applicant_ui
import clipboard_protocol
import realm_resolver

class SettingsTests(unittest.TestCase):
    setUp=test_batch.BatchTests.setUp
    players=test_batch.BatchTests.players
    fetch=test_batch.BatchTests.fetch
    cell=test_applicant_ui.ApplicantUITests.cell

    def install(self):
        root=test_batch.ROOT
        self.lua.execute('return assert(loadstring(...))',(root/'Settings.lua').read_text(encoding='utf-8'))('MPlusLogs',self.mpl)

    def mock_settings(self):
        self.lua.execute('''
            Settings={VarType={Boolean="boolean",String="string",Number="number"},values={},controls={}}
            Settings.RegisterVerticalLayoutCategory=function(name) return {name=name,GetID=function() return 97 end} end
            Settings.RegisterProxySetting=function(category,key,kind,name,default,get,set)
                local entry={key=key,get=get,set=set,default=default,kind=kind}
                Settings.values[key]=entry; return entry
            end
            Settings.CreateCheckbox=function(_,setting) Settings.controls[#Settings.controls+1]=setting end
            Settings.CreateDropdown=function(_,setting,options)
                setting.items=options(); Settings.controls[#Settings.controls+1]=setting
            end
            Settings.CreateControlTextContainer=function()
                return {data={},Add=function(self,key,text) self.data[#self.data+1]={key=key,text=text} end,
                    GetData=function(self) return self.data end}
            end
            Settings.RegisterAddOnCategory=function(category) registeredCategory=category.name end
            Settings.OpenToCategory=function(id) openedCategory=id end
        ''')

    def test_native_category_and_saved_settings(self):
        self.install(); self.mock_settings(); self.mpl.RegisterSettings(); self.mpl.RegisterSettings()
        settings=self.lua.globals().Settings
        self.assertEqual(len(settings.controls),5)
        self.assertEqual(self.lua.globals().registeredCategory,'MPlusLogs')
        values=settings['values']
        self.assertEqual(values.MPLUSLOGS_percentile['get'](),'best')
        self.assertEqual(len(values.MPLUSLOGS_percentile['items']),2)
        self.assertEqual(len(values.MPLUSLOGS_freshHours['items']),4)
        values.MPLUSLOGS_healerHpsFirst['set'](True)
        self.assertTrue(self.lua.globals().MPlusLogsDB.options.healerHpsFirst)
        values.MPLUSLOGS_percentile['set']('median')
        self.assertEqual(self.mpl.GetOption('percentile'),'median')
        self.mpl.OpenSettings(); self.assertEqual(self.lua.globals().openedCategory,97)

    def test_hps_median_switch_updates_rows_summary_and_tooltips_without_refetch(self):
        self.install(); self.mpl.InstallBatchButton()
        _,request=self.mpl.SendBatchRequest(self.players())
        def fetch(args):
            raw=self.fetch(type('Args',(),{'name':'Alice'})())
            character=raw['data']['characterData']['character']; character['name']=args.name
            character['healing']['bestPerformanceAverage']=88
            character['healing']['medianPerformanceAverage']=70
            for row in character['healing']['throughputRankings'].values():
                row['best_historical_percentile']=91; row['median_historical_percentile']=86
            return raw
        response=clipboard_protocol.reply(request,realm_resolver.load_mappings(),self.cache,fetch)
        self.mpl.ReceiveReply(response,True)
        self.mpl.ShowProfile('Alice','Гордунни')
        self.assertEqual(self.mpl.panel.metricHeading.text,'Лучший DPS')
        self.assertIn('62%',self.cell(1).text.text)
        profile=self.mpl.panel.profile
        self.mpl.SetOption('healerHpsFirst',True)
        self.mpl.SetOption('percentile','median')
        self.assertEqual(self.mpl.panel.metricHeading.text,'Лучший HPS')
        self.assertEqual(self.mpl.panel.headings[8].text,'Median %')
        self.assertEqual(self.mpl.panel.headings[9].text,'Best %')
        self.assertIn('70%',self.cell(1).text.text)
        self.assertIn('86|r',self.mpl.panel.rows[1].cells[8].text)
        self.assertIn('91|r',self.mpl.panel.rows[1].cells[9].text)
        self.assertIn('HPS Медианный % в среднем:',self.mpl.panel.summary.text)
        self.mpl.AddTooltip(self.lua.globals().GameTooltip,'Alice','Гордунни')
        self.assertEqual(self.lua.globals().GameTooltip.lines[4][1],'HPS Median / Best')
        self.assertEqual(profile.metric,'hps')
        self.assertEqual(profile.best,88)
        self.assertIsNone(self.mpl.pendingReply)

    def test_age_option_controls_freshness_and_batch_filtering(self):
        self.install()
        self.lua.execute('''
            MPlusLogsDB.profiles[MPlusLogs.Key("Alice","Гордунни")]=
                {updated="2026-10-11 08:00 UTC",metric="dps",dual=true}
        ''')
        profile,_,_=self.mpl.GetProfile('Alice','Гордунни')
        self.assertFalse(self.mpl.IsProfileStale(profile)[0])
        self.mpl.SetOption('freshHours',12)
        self.assertTrue(self.mpl.IsProfileStale(profile)[0])
        pending,skipped=self.mpl.FilterFreshProfiles(self.players())
        self.assertEqual(skipped,0)
        self.mpl.SetOption('freshHours',48)
        pending,skipped=self.mpl.FilterFreshProfiles(self.players())
        self.assertEqual(skipped,1)
        self.assertFalse(self.mpl.SetOption('freshHours',0))
        self.assertFalse(self.mpl.SetOption('percentile','other'))

    def test_popups_and_tooltips_can_be_disabled(self):
        self.install()
        self.mpl.SetOption('tooltips',False)
        self.mpl.AddTooltip(self.lua.globals().GameTooltip,'Киндрих','Гордунни')
        self.assertEqual(len(self.lua.globals().GameTooltip.lines),0)
        self.assertFalse(self.lua.globals().MPlusLogsDB.tooltips)
        self.mpl.SetOption('stalePopup',False)
        profile,_,_=self.mpl.GetProfile('Киндрих','Гордунни')
        profile.updated='2026-10-01 00:00 UTC'
        self.mpl.ShowProfile('Киндрих','Гордунни')
        self.assertIsNone(self.mpl.staleWindow)
        self.assertIn('ff888888',self.mpl.panel.rows[1].cells[8].text)

if __name__=='__main__': unittest.main()
