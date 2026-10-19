# ==============================================================================
# Mariano's Scraper Microsoft Azure PowerShell Deployment Script
# Automatically builds, deploys, and configures bi-weekly execution in Azure
# ==============================================================================

param(
    [string]$ResourceGroup = "rg-marianos-scraper-prod",
    [string]$Location = "eastus",
    [string]$AcrName = ("acrmarianosprod" + (Get-Random -Minimum 1000 -Maximum 9999)),
    [string]$ImageName = "marianos-scraper",
    [string]$Tag = "v1",
    [string]$AciName = "aci-marianos-scraper-job"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 1. Creating Azure Resource Group: $ResourceGroup ===" -ForegroundColor Cyan
az group create --name $ResourceGroup --location $Location

Write-Host "=== 2. Creating Azure Container Registry: $AcrName ===" -ForegroundColor Cyan
az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true

Write-Host "=== 3. Building and Pushing Container Image to ACR ===" -ForegroundColor Cyan
az acr build --registry $AcrName --image "$($ImageName):$($Tag)" -f azure/Dockerfile .

$AcrLoginServer = (az acr show --name $AcrName --query loginServer --output tsv)
$AcrUsername = (az acr credential show --name $AcrName --query username --output tsv)
$AcrPassword = (az acr credential show --name $AcrName --query "passwords[0].value" --output tsv)

Write-Host "=== 4. Launching Azure Container Instance ===" -ForegroundColor Cyan
az container create `
  --resource-group $ResourceGroup `
  --name $AciName `
  --image "$AcrLoginServer/$($ImageName):$($Tag)" `
  --registry-login-server $AcrLoginServer `
  --registry-username $AcrUsername `
  --registry-password $AcrPassword `
  --cpu 2 `
  --memory 4 `
  --restart-policy Never `
  --environment-variables `
      MARIANOS_PROXY_URL="$env:MARIANOS_PROXY_URL" `
      AZURE_STORAGE_CONNECTION_STRING="$env:AZURE_STORAGE_CONNECTION_STRING"

Write-Host "=== Deployment Succeeded! Mariano's container job active in Azure. ===" -ForegroundColor Green
