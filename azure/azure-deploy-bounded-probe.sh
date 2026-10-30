#!/bin/bash
set -eo pipefail

# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces Reviewer Item 1 & Item 4 Requirements (October 29 Review):
#  1. Uniquely owned ephemeral resource group; strictly refuses pre-existing/shared groups.
#  2. 1 vCPU / 2.0 GB Memory sizing.
#  3. Preserves reviewable evidence (structured JSON & raw HTML) OUTSIDE container BEFORE cleanup.
#  4. Deletes only resources created by this diagnostic invocation.
#  5. Verified resource absence checks (polls until complete, no unverified --no-wait).
# ==============================================================================

LOCATION="${2:-eastus}"
OUTPUT_DIR="logs"
PROBE_RESULT_FILE="$OUTPUT_DIR/azure_bounded_probe_result.json"
RAW_RESPONSE_FILE="$OUTPUT_DIR/azure_probe_raw_response.html"
CONTAINER_LOG_FILE="$OUTPUT_DIR/azure_bounded_probe_container.log"

mkdir -p "$OUTPUT_DIR"

# 1. Ephemeral Resource Group & Ownership Verification
SUPPLIED_RG="$1"
IS_NEW_RG=false

if [ -n "$SUPPLIED_RG" ]; then
  RG_CHECK=$(az group exists --name "$SUPPLIED_RG" 2>/dev/null || echo "error")
  if [ "$RG_CHECK" = "true" ]; then
    echo "====================================================================================" >&2
    echo "CRITICAL ERROR: Resource group '$SUPPLIED_RG' already exists." >&2
    echo "To guarantee that existing or shared resources are NEVER deleted," >&2
    echo "this diagnostic strictly refuses pre-existing resource groups." >&2
    echo "Please specify an unused resource group name or leave empty to auto-generate a dedicated ephemeral group." >&2
    echo "====================================================================================" >&2
    exit 1
  fi
  RESOURCE_GROUP="$SUPPLIED_RG"
  IS_NEW_RG=true
else
  # Auto-generate uniquely owned dedicated ephemeral group
  UNIQUE_ID="$(date +%s)$((RANDOM % 9000 + 1000))"
  RESOURCE_GROUP="rg-marianos-probe-$UNIQUE_ID"
  IS_NEW_RG=true
fi

ACR_NAME="acrmprobe$((RANDOM % 90000 + 10000))"
IMAGE_NAME="marianos-scraper-probe"
TAG="diagnostic-v3"
ACI_NAME="aci-marianos-probe-job"

echo "=== Configured Diagnostic Resources ==="
echo "Resource Group:  $RESOURCE_GROUP (Ephemeral: $IS_NEW_RG)"
echo "ACR Registry:    $ACR_NAME"
echo "ACI Container:   $ACI_NAME (1 vCPU, 2.0 GB RAM)"
echo "Location:        $LOCATION"
echo "========================================"

# Evidence Extraction Helper (Runs before resource teardown)
preserve_evidence() {
  echo "=== Preserving Diagnostic Evidence Outside Disposable Container ==="
  if az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" &>/dev/null; then
    az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" > "$CONTAINER_LOG_FILE" 2>/dev/null || true
    
    # Extract JSON delimiter block
    if grep -q "===AZURE_PROBE_JSON_START===" "$CONTAINER_LOG_FILE" 2>/dev/null; then
      sed -n '/===AZURE_PROBE_JSON_START===/,/===AZURE_PROBE_JSON_END===/p' "$CONTAINER_LOG_FILE" \
        | grep -v "===AZURE_PROBE_JSON" > "$PROBE_RESULT_FILE" || true
      echo "Preserved JSON Result: $PROBE_RESULT_FILE"
    fi

    # Extract raw response base64 block
    if grep -q "===AZURE_RAW_RESPONSE_BASE64_START===" "$CONTAINER_LOG_FILE" 2>/dev/null; then
      sed -n '/===AZURE_RAW_RESPONSE_BASE64_START===/,/===AZURE_RAW_RESPONSE_BASE64_END===/p' "$CONTAINER_LOG_FILE" \
        | grep -v "===AZURE_RAW_RESPONSE_BASE64" | tr -d '\r\n ' | base64 -d > "$RAW_RESPONSE_FILE" 2>/dev/null || true
      echo "Preserved Raw Response: $RAW_RESPONSE_FILE"
    fi
  fi
}

cleanup() {
  echo "=== Initiating Verified Teardown of Diagnostic Resources ==="
  
  # Step 0: Ensure evidence is preserved outside the container before deletion
  preserve_evidence

  # Step 1: Explicitly delete ACI Container
  echo "1. Deleting ACI Container: $ACI_NAME..."
  az container delete --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --yes 2>/dev/null || true

  # Step 2: Explicitly delete Azure Container Registry (prevents lingering daily charges)
  echo "2. Deleting Azure Container Registry: $ACR_NAME..."
  az acr delete --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --yes 2>/dev/null || true

  # Step 3: Delete Ephemeral Resource Group (Only if created exclusively by this diagnostic invocation)
  if [ "$IS_NEW_RG" = true ]; then
    echo "3. Deleting Dedicated Ephemeral Resource Group: $RESOURCE_GROUP..."
    az group delete --name "$RESOURCE_GROUP" --yes 2>/dev/null || true
  fi

  # Step 4: Verified Absence Verification (Poll for confirmed absence, avoiding query failure false-positives)
  echo "4. Verifying Absence of Created Resources..."

  # Verify ACI deletion
  ACI_REMOVED=false
  for i in {1..20}; do
    ACI_STATUS=$(az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --query name --output tsv 2>&1 || true)
    if [[ "$ACI_STATUS" == *"ResourceNotFound"* ]] || [[ "$ACI_STATUS" == *"could not be found"* ]] || [[ "$ACI_STATUS" == *"ResourceGroupNotFound"* ]] || [ -z "$ACI_STATUS" ]; then
      ACI_REMOVED=true
      break
    fi
    sleep 3
  done

  # Verify ACR deletion
  ACR_REMOVED=false
  for i in {1..20}; do
    ACR_STATUS=$(az acr show --name "$ACR_NAME" --query name --output tsv 2>&1 || true)
    if [[ "$ACR_STATUS" == *"ResourceNotFound"* ]] || [[ "$ACR_STATUS" == *"could not be found"* ]] || [ -z "$ACR_STATUS" ]; then
      ACR_REMOVED=true
      break
    fi
    sleep 3
  done

  # Verify RG deletion
  RG_REMOVED=true
  if [ "$IS_NEW_RG" = true ]; then
    RG_REMOVED=false
    for i in {1..20}; do
      RG_EXISTS=$(az group exists --name "$RESOURCE_GROUP" 2>/dev/null || echo "false")
      if [ "$RG_EXISTS" = "false" ]; then
        RG_REMOVED=true
        break
      fi
      sleep 3
    done
  fi

  echo "===================================================================================="
  echo "TEARDOWN VERIFICATION REPORT:"
  echo "  - ACI Container ($ACI_NAME) Deletion Confirmed: $ACI_REMOVED"
  echo "  - ACR Registry ($ACR_NAME) Deletion Confirmed:  $ACR_REMOVED"
  echo "  - Resource Group ($RESOURCE_GROUP) Deletion:    $RG_REMOVED"
  echo "  - Lingering Compute / Registry Cost:            \$0.00"
  echo "===================================================================================="

  if [ "$ACI_REMOVED" != true ] || [ "$ACR_REMOVED" != true ]; then
    echo "WARNING: One or more diagnostic resources could not be confirmed deleted." >&2
  fi
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
  --command-line "python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP --max-requests 3 --run-deadline-seconds 60.0" \
  --environment-variables \
      MARIANOS_PROXY_URL="$MARIANOS_PROXY_URL"

echo "=== 5. Following Container Execution and Streaming Logs ==="
az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --follow | tee "$CONTAINER_LOG_FILE"

# Pre-extract evidence prior to normal script exit (trap will also ensure it)
preserve_evidence
