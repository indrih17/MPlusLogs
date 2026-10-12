-- MPlusLogs controlled LoadOnDemand probe payload
MPlusLogsProbePayloads = MPlusLogsProbePayloads or {}
MPlusLogsProbeLoads = MPlusLogsProbeLoads or {}
MPlusLogsProbePayloads.A = {value="BASELINE-A"}
MPlusLogsProbeLoads.A = (MPlusLogsProbeLoads.A or 0) + 1
