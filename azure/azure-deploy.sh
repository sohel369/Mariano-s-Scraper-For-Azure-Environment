#!/bin/bash
set -e

# ==============================================================================
# Mariano's Scraper Microsoft Azure Deployment Script
# Automatically builds, deploys, and configures twice-per-week execution in Azure
# ==============================================================================

RESOURCE_GROUP="rg-marianos-scraper-prod"
LOCATION="eastus"
ACR_NAME="acrmarianosscraperprod$RANDOM"
IMAGE_NAME="marianos-scraper"
TAG="v1"
ACI_NAME="aci-marianos-scraper-job"

echo "=== 1. Creating Resource Group in Azure: $RESOURCE_GROUP ==="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

echo "=== 2. Creating Azure Container Registry (ACR): $ACR_NAME ==="
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true

echo "=== 3. Building and Pushing Docker Image to ACR ==="
az acr build --registry "$ACR_NAME" --image "$IMAGE_NAME:$TAG" -f azure/Dockerfile .

ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer --output tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" --output tsv)
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username --output tsv)

echo "=== 3.1 Provisioning Persistent Azure Storage and Seeding Input CSV ==="
STORAGE_ACCOUNT_NAME="samarianos$RANDOM"
az storage account create --resource-group "$RESOURCE_GROUP" --name "$STORAGE_ACCOUNT_NAME" --location "$LOCATION" --sku Standard_LRS
STORAGE_KEY=$(az storage account keys list --resource-group "$RESOURCE_GROUP" --account-name "$STORAGE_ACCOUNT_NAME" --query "[0].value" --output tsv)
az storage share create --name "marianos-scraper-share" --account-name "$STORAGE_ACCOUNT_NAME" --account-key "$STORAGE_KEY"
az storage directory create --name "input" --share-name "marianos-scraper-share" --account-name "$STORAGE_ACCOUNT_NAME" --account-key "$STORAGE_KEY"
az storage file upload --source "data/input/Marianos_Category_URLs.csv" --share-name "marianos-scraper-share" --path "input/Marianos_Category_URLs.csv" --account-name "$STORAGE_ACCOUNT_NAME" --account-key "$STORAGE_KEY"

echo "=== 4. Deploying Scheduled Container Job to Azure Container Instances ==="
az container create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACI_NAME" \
  --image "$ACR_LOGIN_SERVER/$IMAGE_NAME:$TAG" \
  --registry-login-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --cpu 1 \
  --memory 2 \
  --restart-policy Never \
  --azure-file-volume-account-name "$STORAGE_ACCOUNT_NAME" \
  --azure-file-volume-account-key "$STORAGE_KEY" \
  --azure-file-volume-share-name "marianos-scraper-share" \
  --azure-file-volume-mount-path "/app/data" \
  --environment-variables \
      MARIANOS_PROXY_URL="$MARIANOS_PROXY_URL" \
      AZURE_STORAGE_CONNECTION_STRING="$AZURE_STORAGE_CONNECTION_STRING"

echo "=== 5. Deploying Twice-Per-Week Logic App Trigger Workflow ==="
az logic workflow create \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --name "logic-marianos-cron-trigger" \
  --definition "azure/azure-cron-schedule.json"

echo "=== Azure Deployment Completed Successfully! ==="
echo "ACR Registry: $ACR_LOGIN_SERVER"
echo "Container: $ACI_NAME"
echo "Schedule: Twice-per-week via Logic Apps (Sunday & Wednesday 04:00 UTC)"
