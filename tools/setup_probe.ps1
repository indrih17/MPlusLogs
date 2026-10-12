param([ValidateSet('Install','Update','Reset')][string]$Phase = 'Install')
$ErrorActionPreference = 'Stop'
$probeWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$probeAddons = [IO.Path]::GetFullPath((Join-Path $probeWorkspace '..'))
if ((Split-Path $probeWorkspace -Leaf) -ne 'MPlusLogs' -or (Split-Path $probeAddons -Leaf) -ne 'AddOns') {
    throw 'Run this script from the installed AddOns/MPlusLogs/tools directory.'
}
$probeNonce = [Guid]::NewGuid().ToString('N').Substring(0,12)
foreach ($probeSlot in @('A','B')) {
    $probeName = "MPlusLogsProbe_$probeSlot"
    $probeTarget = [IO.Path]::GetFullPath((Join-Path $probeAddons $probeName))
    if ((Split-Path $probeTarget -Parent) -ne $probeAddons) { throw 'Probe path left AddOns.' }
    $probePayload = Join-Path $probeTarget 'Payload.lua'
    if (Test-Path -LiteralPath $probeTarget) {
        if (-not (Test-Path -LiteralPath $probePayload) -or -not ((Get-Content -LiteralPath $probePayload -TotalCount 1) -eq '-- MPlusLogs controlled LoadOnDemand probe payload')) {
            throw "Refusing to overwrite unrecognized folder $probeTarget"
        }
    } elseif ($Phase -ne 'Install') { throw "Probe is not installed: $probeTarget" }
    if ($Phase -eq 'Install') {
        New-Item -ItemType Directory -Path $probeTarget -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $probeWorkspace "experiments\ondemand\$probeName\$probeName.toc") -Destination (Join-Path $probeTarget "$probeName.toc")
    }
    if ($Phase -eq 'Update') {
        $probeValue = "UPDATED-$probeSlot-$probeNonce"
        $probeContent = @"
-- MPlusLogs controlled LoadOnDemand probe payload
MPlusLogsProbePayloads = MPlusLogsProbePayloads or {}
MPlusLogsProbeLoads = MPlusLogsProbeLoads or {}
MPlusLogsProbePayloads.$probeSlot = {value="$probeValue"}
MPlusLogsProbeLoads.$probeSlot = (MPlusLogsProbeLoads.$probeSlot or 0) + 1
"@
        [IO.File]::WriteAllText($probePayload, $probeContent, [Text.UTF8Encoding]::new($false))
    } else {
        Copy-Item -LiteralPath (Join-Path $probeWorkspace "experiments\ondemand\$probeName\Payload.lua") -Destination $probePayload
    }
    Write-Output "$Phase $probeName"
    if ($Phase -eq 'Update') { Write-Output "Expected new value: $probeValue" }
    Get-FileHash -LiteralPath $probePayload -Algorithm SHA256 | Select-Object Path,Hash
}
