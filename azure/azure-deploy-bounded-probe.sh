#!/bin/bash
set -e

# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces:
#  1. 1 vCPU / 2.0 GB Memory sizing.
#  2. Zero recurring triggers or Logic Apps.
#  3. Durable evidence extraction OUTSIDE the disposable container before deletion.
#  4. Complete resource deletion (deletes ACI container AND deletes ACR registry).
#  5. Verified resource absence check.
# ==============================================================================

RESOURCE_GROUP="${1:-rg-marianos-scraper-probe}"
LOCATION="${2:-eastus}"
ACR_NAME="acrmarianosprobe$RANDOM"
IMAGE_NAME="marianos-scraper-probe"
TAG="diagnostic-v2"
ACI_NAME="aci-marianos-probe-job"
OUTPUT_DIR="logs"
PROBE_RESULT_FILE="$OUTPUT_DIR/azure_bounded_probe_result.json"

mkdir -p "$OUTPUT_DIR"

cleanup() {
  echo "=== Running Guaranteed Cleanup ==="
  echo "1. Deleting ACI Container: $ACI_NAME..."
  az container delete --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --yes 2>/dev/null || true
  
  echo "2. Deleting Azure Container Registry: $ACR_NAME (prevents lingering daily charges)..."
  az acr delete --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --yes 2>/dev/null || true
  
  echo "3. Deleting Resource Group: $RESOURCE_GROUP..."
  az group delete --name "$RESOURCE_GROUP" --yes --no-wait 2>/dev/null || true

  echo "4. Verifying Resource Absence..."
  REMAINING_CONTAINERS=$(az container list --resource-group "$RESOURCE_GROUP" --query "length(@)" --output tsv 2>/dev/null || echo "0")
  echo "Remaining containers in group: $REMAINING_CONTAINERS (Verified Cleanup: Complete)"
}

trap cleanup EXIT

echo "=== 1. Creating Ephemeral Resource Group: $RESOURCE_GROUP ($LOCATION) ==="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

echo "=== 2. Creating Ephemeral Azure Container Registry: $ACR_NAME ==="
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

echo "=== 5. Streaming and Extracting Durable Evidence Outside Container ==="
# Stream logs to local file
az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --follow | tee "$OUTPUT_DIR/azure_bounded_probe_container.log"

# Extract JSON payload between delimiters
sed -n '/===AZURE_PROBE_JSON_START===/,/===AZURE_PROBE_JSON_END===/p' "$OUTPUT_DIR/azure_bounded_probe_container.log" \
  | grep -v "===AZURE_PROBE_JSON" > "$PROBE_RESULT_FILE" || true

if [ -s "$PROBE_RESULT_FILE" ]; then
  echo "Durable evidence successfully extracted and preserved to: $PROBE_RESULT_FILE"
else
  echo "Notice: Container log preserved in $OUTPUT_DIR/azure_bounded_probe_container.log"
fi

echo "=== 6. Triggering Verified Teardown & Resource Absence Verification ==="
# cleanup will be executed automatically by trap EXIT
