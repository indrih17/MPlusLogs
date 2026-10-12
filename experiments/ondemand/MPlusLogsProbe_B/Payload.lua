-- MPlusLogs controlled LoadOnDemand probe payload
MPlusLogsProbePayloads = MPlusLogsProbePayloads or {}
MPlusLogsProbeLoads = MPlusLogsProbeLoads or {}
MPlusLogsProbePayloads.B = {value="BASELINE-B"}
MPlusLogsProbeLoads.B = (MPlusLogsProbeLoads.B or 0) + 1
