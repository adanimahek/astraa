$ErrorActionPreference = "Stop"

$sumoRoot = Split-Path -Parent $PSScriptRoot
$netconvert = Get-Command netconvert -ErrorAction Stop

Push-Location $sumoRoot
try {
    & $netconvert.Source `
        --node-files ".\network\intersection.nod.xml" `
        --edge-files ".\network\intersection.edg.xml" `
        --output-file ".\network\intersection.net.xml" `
        --tls.default-type static `
        --no-turnarounds true

    if ($LASTEXITCODE -ne 0) {
        throw "netconvert failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
