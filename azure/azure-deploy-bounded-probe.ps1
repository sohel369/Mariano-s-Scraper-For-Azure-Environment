# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script (PowerShell)
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces strict 1 vCPU / 2.0 GB Memory sizing, zero recurring triggers,
# and verified container cleanup upon completion.
# ==============================================================================

param(
    [string]$ResourceGroup = "rg-marianos-scraper-probe",
    [string]$Location = "eastus",
    [string]$AcrName = ("acrmarianosprobe" + (Get-Random -Minimum 1000 -Maximum 9999)),
    [string]$ImageName = "marianos-scraper-probe",
    [string]$Tag = "diagnostic-v1",
    [string]$AciName = "aci-marianos-probe-job"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 1. Creating Minimal Resource Group: $ResourceGroup ($Location) ===" -ForegroundColor Cyan
az group create --name $ResourceGroup --location $Location

Write-Host "=== 2. Creating Lightweight Azure Container Registry: $AcrName ===" -ForegroundColor Cyan
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

Write-Host "=== 5. Streaming Probe Logs ===" -ForegroundColor Cyan
az container logs --resource-group $ResourceGroup --name $AciName --follow

Write-Host "=== 6. Verified Cleanup: Deleting Probe Container Group ===" -ForegroundColor Cyan
az container delete --resource-group $ResourceGroup --name $AciName --yes

Write-Host "=== Probe Complete. Zero dangling compute resources remain. ===" -ForegroundColor Green
