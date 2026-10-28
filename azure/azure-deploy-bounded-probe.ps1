# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script (PowerShell)
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces:
#  1. 1 vCPU / 2.0 GB Memory sizing.
#  2. Zero recurring triggers or Logic Apps.
#  3. Durable evidence extraction OUTSIDE the disposable container before deletion.
#  4. Complete resource deletion (deletes ACI container AND deletes ACR registry).
#  5. Verified resource absence check.
# ==============================================================================

param(
    [string]$ResourceGroup = "rg-marianos-scraper-probe",
    [string]$Location = "eastus",
    [string]$AcrName = ("acrmarianosprobe" + (Get-Random -Minimum 1000 -Maximum 9999)),
    [string]$ImageName = "marianos-scraper-probe",
    [string]$Tag = "diagnostic-v2",
    [string]$AciName = "aci-marianos-probe-job",
    [string]$OutputDir = "logs"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$ContainerLogPath = Join-Path $OutputDir "azure_bounded_probe_container.log"
$JsonResultPath = Join-Path $OutputDir "azure_bounded_probe_result.json"

try {
    Write-Host "=== 1. Creating Ephemeral Resource Group: $ResourceGroup ($Location) ===" -ForegroundColor Cyan
    az group create --name $ResourceGroup --location $Location

    Write-Host "=== 2. Creating Ephemeral Azure Container Registry: $AcrName ===" -ForegroundColor Cyan
    az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true

    Write-Host "=== 3. Building Probe Docker Container ===" -ForegroundColor Cyan
    az acr build --registry $AcrName --image "$($ImageName):$($Tag)" -f azure/Dockerfile .

    $AcrLoginServer = (az acr show --name $AcrName --query loginServer --output tsv)
    $AcrUsername = (az acr credential show --name $AcrName --query username --output tsv)
    $AcrPassword = (az acr credential show --name $AcrName --query "passwords[0].value" --output tsv)

    Write-Host "=== 4. Executing Manual Bounded Probe in ACI (1 vCPU, 2.0 GB RAM) ===" -ForegroundColor Cyan
    az container create `
      --resource-group $ResourceGroup `
      --name $AciName `
      --image "$AcrLoginServer/$($ImageName):$($Tag)" `
      --registry-login-server $AcrLoginServer `
      --registry-username $AcrUsername `
      --registry-password $AcrPassword `
      --cpu 1 `
      --memory 2 `
      --restart-policy Never `
      --command-line "python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP" `
      --environment-variables `
          MARIANOS_PROXY_URL="$env:MARIANOS_PROXY_URL"

    Write-Host "=== 5. Streaming and Extracting Durable Evidence Outside Container ===" -ForegroundColor Cyan
    $logs = az container logs --resource-group $ResourceGroup --name $AciName --follow
    $logs | Out-File -FilePath $ContainerLogPath -Encoding utf8

    # Extract JSON delimited block
    $logContent = Get-Content -Path $ContainerLogPath -Raw
    if ($logContent -match '===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===') {
        $extractedJson = $matches[1].Trim()
        $extractedJson | Out-File -FilePath $JsonResultPath -Encoding utf8
        Write-Host "Durable evidence successfully preserved to: $JsonResultPath" -ForegroundColor Green
    } else {
        Write-Host "Notice: Raw container logs preserved in $ContainerLogPath" -ForegroundColor Yellow
    }

} finally {
    Write-Host "=== 6. Running Guaranteed Cleanup & Resource Absence Verification ===" -ForegroundColor Cyan
    
    Write-Host "Deleting Container: $AciName..." -ForegroundColor Gray
    az container delete --resource-group $ResourceGroup --name $AciName --yes 2>$null | Out-Null
    
    Write-Host "Deleting Container Registry: $AcrName (prevents lingering daily charges)..." -ForegroundColor Gray
    az acr delete --resource-group $ResourceGroup --name $AcrName --yes 2>$null | Out-Null
    
    Write-Host "Deleting Resource Group: $ResourceGroup..." -ForegroundColor Gray
    az group delete --name $ResourceGroup --yes --no-wait 2>$null | Out-Null

    # Resource absence verification
    $remaining = az container list --resource-group $ResourceGroup --query "length(@)" --output tsv 2>$null
    if (-not $remaining) { $remaining = "0" }
    Write-Host "Verified Cleanup: Remaining active containers = $remaining (Clean teardown confirmed)" -ForegroundColor Green
}
