"""Probe state machine checks. These cannot verify WoW's file cache behavior."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / ".test-deps"))
from lupa.lua51 import LuaRuntime
from test_addon import MOCK, load_locales


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.mpl = self.lua.table()
        load_locales(self.lua,self.mpl)
        self.lua.execute('''
            function GetBuildInfo() return "test", "test-build", "", 120100 end
            loadedProbes = {}
            diskValues = {A="BASELINE-A", B="BASELINE-B"}
            C_AddOns = {}
            function C_AddOns.IsAddOnLoaded(name) return loadedProbes[name] or false end
            function C_AddOns.LoadAddOn(name)
                if loadedProbes[name] then return true end
                local slot = name:match("_([AB])$")
                if not slot then return false,"MISSING" end
                MPlusLogsProbePayloads = MPlusLogsProbePayloads or {}
                MPlusLogsProbeLoads = MPlusLogsProbeLoads or {}
                MPlusLogsProbePayloads[slot] = {value=diskValues[slot]}
                MPlusLogsProbeLoads[slot] = (MPlusLogsProbeLoads[slot] or 0) + 1
                loadedProbes[name] = true
                return true
            end
        ''')
        self.lua.execute("return assert(loadstring(...))", (ROOT / "Probe.lua").read_text(encoding="utf-8"))("MPlusLogs",self.mpl)

    def test_window_does_not_load_probe(self):
        self.mpl.ShowProbe()
        self.assertFalse(self.lua.globals().C_AddOns.IsAddOnLoaded("MPlusLogsProbe_A"))
        self.assertFalse(self.lua.globals().C_AddOns.IsAddOnLoaded("MPlusLogsProbe_B"))

    def test_positive_requires_new_a_and_unchanged_control(self):
        self.mpl.ProbePrepare()
        self.assertTrue(self.mpl.probeState.prepared)
        self.assertFalse(self.lua.globals().C_AddOns.IsAddOnLoaded("MPlusLogsProbe_A"))
        self.lua.execute('diskValues.A="UPDATED-A-abc123"; diskValues.B="UPDATED-B-abc123"')
        self.mpl.ProbeRead()
        self.assertTrue(self.mpl.probeState.result.startswith("PASS:"))
        self.assertEqual(self.lua.globals().MPlusLogsProbeLoads.B,1)
        self.assertEqual(self.lua.globals().MPlusLogsProbePayloads.B.value,"BASELINE-B")

    def test_baseline_is_not_false_success(self):
        self.mpl.ProbePrepare()
        self.mpl.ProbeRead()
        self.assertTrue(self.mpl.probeState.result.startswith("BASELINE:"))

    def test_preloaded_a_rejects_experiment(self):
        self.lua.globals().C_AddOns.LoadAddOn("MPlusLogsProbe_A")
        self.mpl.ProbePrepare()
        self.assertFalse(self.mpl.probeState.prepared)

    def test_probe_payloads_compile_and_execute_once(self):
        for slot in ("A","B"):
            file=ROOT / f"experiments/ondemand/MPlusLogsProbe_{slot}/Payload.lua"
            self.lua.execute("return assert(loadstring(...))",file.read_text(encoding="utf-8"))()
            self.assertEqual(self.lua.globals().MPlusLogsProbePayloads[slot].value,f"BASELINE-{slot}")
            self.assertEqual(self.lua.globals().MPlusLogsProbeLoads[slot],1)


if __name__ == "__main__":
    unittest.main()
