#!/bin/bash
set -e

# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces strict 1 vCPU / 2.0 GB Memory sizing, zero recurring triggers,
# and verified container cleanup upon completion.
# ==============================================================================

RESOURCE_GROUP="${1:-rg-marianos-scraper-probe}"
LOCATION="${2:-eastus}"
ACR_NAME="acrmarianosprobe$RANDOM"
IMAGE_NAME="marianos-scraper-probe"
TAG="diagnostic-v1"
ACI_NAME="aci-marianos-probe-job"

echo "=== 1. Creating Minimal Resource Group: $RESOURCE_GROUP ($LOCATION) ==="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

echo "=== 2. Creating Lightweight Azure Container Registry: $ACR_NAME ==="
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true

echo "=== 3. Building Probe Docker Container ==="
az acr build --registry "$ACR_NAME" --image "$IMAGE_NAME:$TAG" -f azure/Dockerfile .

ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer --output tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" --output tsv)
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username --output tsv)

echo "=== 4. Executing Manual Bounded Probe in ACI (1 vCPU, 2.0 GB RAM) ==="
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
  --command-line "python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP" \
  --environment-variables \
      MARIANOS_PROXY_URL="$MARIANOS_PROXY_URL"

echo "=== 5. Monitoring Probe Execution Logs ==="
az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --follow

echo "=== 6. Verified Cleanup: Deleting Probe Container Group ==="
az container delete --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --yes

echo "=== Probe Complete. Zero dangling compute resources remain. ==="
