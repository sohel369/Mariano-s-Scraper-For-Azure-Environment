# ==============================================================================
# Mariano's Scraper Microsoft Azure PowerShell Deployment Script
# Automatically builds, deploys, provisions Storage & RBAC Managed Identity,
# and configures bi-weekly execution in Azure Container Instances & Logic Apps
# ==============================================================================

param(
    [string]$ResourceGroup = "rg-marianos-scraper-prod",
    [string]$Location = "eastus",
    [string]$AcrName = ("acrmarianosprod" + (Get-Random -Minimum 1000 -Maximum 9999)),
    [string]$StorageAccountName = ("stmarianos" + (Get-Random -Minimum 1000 -Maximum 9999)),
    [string]$ContainerName = "marianos-scraped-data",
    [string]$IdentityName = "id-marianos-scraper-prod",
    [string]$ImageName = "marianos-scraper",
    [string]$Tag = "v2-prod",
    [string]$AciName = "aci-marianos-scraper-job"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 1. Creating Azure Resource Group: $ResourceGroup ===" -ForegroundColor Cyan
az group create --name $ResourceGroup --location $Location

Write-Host "=== 2. Provisioning Azure Storage Account & Blob Container ===" -ForegroundColor Cyan
az storage account create `
  --resource-group $ResourceGroup `
  --name $StorageAccountName `
  --location $Location `
  --sku Standard_LRS `
  --encryption-services blob `
  --allow-blob-public-access false

$StorageConnString = (az storage account show-connection-string --name $StorageAccountName --resource-group $ResourceGroup --query connectionString --output tsv)
$StorageId = (az storage account show --name $StorageAccountName --resource-group $ResourceGroup --query id --output tsv)

az storage container create `
  --account-name $StorageAccountName `
  --name $ContainerName `
  --connection-string $StorageConnString

Write-Host "=== 3. Creating User-Assigned Managed Identity & RBAC Roles ===" -ForegroundColor Cyan
az identity create --resource-group $ResourceGroup --name $IdentityName
$IdentityId = (az identity show --resource-group $ResourceGroup --name $IdentityName --query id --output tsv)
$PrincipalId = (az identity show --resource-group $ResourceGroup --name $IdentityName --query principalId --output tsv)

# Role assignment: Storage Blob Data Contributor on Storage Account
az role assignment create `
  --assignee-object-id $PrincipalId `
  --role "Storage Blob Data Contributor" `
  --scope $StorageId `
  --assignee-principal-type ServicePrincipal

Write-Host "=== 4. Creating Azure Container Registry: $AcrName ===" -ForegroundColor Cyan
az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true
$AcrId = (az acr show --name $AcrName --resource-group $ResourceGroup --query id --output tsv)

# Role assignment: AcrPull on Azure Container Registry
az role assignment create `
  --assignee-object-id $PrincipalId `
  --role "AcrPull" `
  --scope $AcrId `
  --assignee-principal-type ServicePrincipal

Write-Host "=== 5. Building and Pushing Container Image to ACR ===" -ForegroundColor Cyan
az acr build --registry $AcrName --image "$($ImageName):$($Tag)" -f azure/Dockerfile .

$AcrLoginServer = (az acr show --name $AcrName --query loginServer --output tsv)
$AcrUsername = (az acr credential show --name $AcrName --query username --output tsv)
$AcrPassword = (az acr credential show --name $AcrName --query "passwords[0].value" --output tsv)

Write-Host "=== 6. Launching Production Azure Container Instance ===" -ForegroundColor Cyan
az container create `
  --resource-group $ResourceGroup `
  --name $AciName `
  --image "$AcrLoginServer/$($ImageName):$($Tag)" `
  --registry-login-server $AcrLoginServer `
  --registry-username $AcrUsername `
  --registry-password $AcrPassword `
  --assign-identity $IdentityId `
  --cpu 2 `
  --memory 4 `
  --restart-policy Never `
  --environment-variables `
      MARIANOS_PROXY_URL="$env:MARIANOS_PROXY_URL" `
      AZURE_STORAGE_CONNECTION_STRING="$StorageConnString" `
      AZURE_STORAGE_CONTAINER="$ContainerName"

Write-Host "=== 7. Deploying Bi-Weekly Logic App Trigger Workflow ===" -ForegroundColor Cyan
$SubId = (az account show --query id --output tsv)

# Create Logic App with parameter overrides for current Azure subscription & resource group
$LogicAppParams = @{
    subscriptionId = @{ value = $SubId }
    resourceGroup = @{ value = $ResourceGroup }
    containerGroupName = @{ value = $AciName }
} | ConvertTo-Json -Compress

az logic workflow create `
  --resource-group $ResourceGroup `
  --location $Location `
  --name "logic-marianos-cron-trigger" `
  --definition "azure/azure-cron-schedule.json"

# Assign Managed Identity permissions to allow Logic App to trigger Container Group Start
$LogicAppPrincipalId = (az logic workflow show --resource-group $ResourceGroup --name "logic-marianos-cron-trigger" --query "identity.principalId" --output tsv 2>$null)
if ($LogicAppPrincipalId) {
    az role assignment create `
      --assignee-object-id $LogicAppPrincipalId `
      --role "Contributor" `
      --scope "/subscriptions/$SubId/resourceGroups/$ResourceGroup/providers/Microsoft.ContainerInstance/containerGroups/$AciName" `
      --assignee-principal-type ServicePrincipal
}

Write-Host "=== Deployment Succeeded! Mariano's container job, storage blob container, and bi-weekly schedule active in Azure. ===" -ForegroundColor Green
