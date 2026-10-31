#!/bin/bash
set -eo pipefail

# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces Reviewer Item 1 & Item 2 Requirements (October 31 Review):
#  1. Uniquely owned ephemeral resource group; strictly refuses pre-existing/shared groups.
#  2. Safe error handling: Failed existence check stops immediately; does not assume permission.
#  3. Explicit resource ownership tracking: Deletes only resources created by this invocation.
#  4. Complete absence verification: Confirms deletion of ACI, ACR, AND Resource Group.
#  5. Durable evidence validation: Fresh run isolation, strict start/end delimiters,
#     SHA-256 and byte-count integrity check of raw response body.
#  6. Stage-separated reporting: Reports Probe Execution, Evidence Export, and Resource Teardown,
#     exiting non-zero if ANY stage fails.
# ==============================================================================

# Execution and resource state flags
RG_CREATED=false
ACR_CREATED=false
ACI_CREATED=false
PROBE_SUCCESS=false
EXPORT_VERIFIED=false
ALL_REMOVED=false
CONTAINER_EXIT_CODE=1

SUPPLIED_RG="$1"
LOCATION="${2:-eastus}"
OUTPUT_DIR="logs"
RUN_ID="$(date +%Y%m%d_%H%M%S)_$((RANDOM % 9000 + 1000))"
PROBE_RESULT_FILE="$OUTPUT_DIR/azure_bounded_probe_result.json"
RAW_RESPONSE_FILE="$OUTPUT_DIR/azure_probe_raw_response.html"
CONTAINER_LOG_FILE="$OUTPUT_DIR/azure_bounded_probe_container.log"

mkdir -p "$OUTPUT_DIR"

# Pre-execution cleanup: Strictly remove stale result files to prevent false verification from previous runs
rm -f "$PROBE_RESULT_FILE" "$RAW_RESPONSE_FILE" "$CONTAINER_LOG_FILE"

# 1. Ephemeral Resource Group & Ownership Verification
if [ -n "$SUPPLIED_RG" ]; then
  # Explicit absence check with strict exit-code handling
  set +e
  RG_EXISTS=$(az group exists --name "$SUPPLIED_RG" 2>/dev/null)
  CHECK_STATUS=$?
  set -e

  if [ $CHECK_STATUS -ne 0 ]; then
    echo "====================================================================================" >&2
    echo "CRITICAL ERROR: Failed to query resource group existence (exit code $CHECK_STATUS)." >&2
    echo "Refusing to proceed to prevent accidental modification of shared resources." >&2
    echo "====================================================================================" >&2
    exit 1
  fi

  RG_EXISTS_CLEAN=$(echo "$RG_EXISTS" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
  if [ "$RG_EXISTS_CLEAN" = "true" ]; then
    echo "====================================================================================" >&2
    echo "CRITICAL ERROR: Resource group '$SUPPLIED_RG' already exists." >&2
    echo "To guarantee that existing or shared resources are NEVER deleted," >&2
    echo "this diagnostic strictly refuses pre-existing resource groups." >&2
    echo "Please specify an unused resource group name or omit parameter to auto-generate." >&2
    echo "====================================================================================" >&2
    exit 1
  elif [ "$RG_EXISTS_CLEAN" != "false" ]; then
    echo "CRITICAL ERROR: Unknown/error response from az group exists: '$RG_EXISTS'." >&2
    exit 1
  fi
  RESOURCE_GROUP="$SUPPLIED_RG"
else
  # Auto-generate uniquely owned dedicated ephemeral group
  RESOURCE_GROUP="rg-marianos-probe-$RUN_ID"
fi

ACR_NAME="acrmprobe$((RANDOM % 90000 + 10000))"
IMAGE_NAME="marianos-scraper-probe"
TAG="diagnostic-v3"
ACI_NAME="aci-marianos-probe-job"

echo "=== Configured Diagnostic Resources ==="
echo "Run Identifier:  $RUN_ID"
echo "Resource Group:  $RESOURCE_GROUP (Ephemeral)"
echo "ACR Registry:    $ACR_NAME"
echo "ACI Container:   $ACI_NAME (1 vCPU, 2.0 GB RAM)"
echo "Location:        $LOCATION"
echo "========================================"

# Evidence Extraction & Validation Helper (Runs before resource teardown)
preserve_and_validate_evidence() {
  echo "=== Preserving Diagnostic Evidence Outside Disposable Container ==="
  if [ "$ACI_CREATED" = true ]; then
    # Bounded recovery path: If log file does not exist or delimiters missing, retry fetching logs
    for attempt in 1 2 3; do
      if [ ! -s "$CONTAINER_LOG_FILE" ] || ! grep -q "===AZURE_PROBE_JSON_START===" "$CONTAINER_LOG_FILE" 2>/dev/null; then
        echo "Fetching container logs from Azure (attempt $attempt/3)..."
        az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" > "$CONTAINER_LOG_FILE" 2>/dev/null || true
      fi
      if grep -q "===AZURE_PROBE_JSON_START===" "$CONTAINER_LOG_FILE" 2>/dev/null && grep -q "===AZURE_PROBE_JSON_END===" "$CONTAINER_LOG_FILE" 2>/dev/null; then
        break
      fi
      sleep 2
    done

    # Extract JSON delimiter block ONLY if BOTH start and end delimiters exist
    if grep -q "===AZURE_PROBE_JSON_START===" "$CONTAINER_LOG_FILE" 2>/dev/null && grep -q "===AZURE_PROBE_JSON_END===" "$CONTAINER_LOG_FILE" 2>/dev/null; then
      sed -n '/===AZURE_PROBE_JSON_START===/,/===AZURE_PROBE_JSON_END===/p' "$CONTAINER_LOG_FILE" \
        | grep -v "===AZURE_PROBE_JSON" > "$PROBE_RESULT_FILE" || true
    else
      echo "WARNING: Incomplete or missing JSON delimiters in container log." >&2
      rm -f "$PROBE_RESULT_FILE"
    fi

    # Extract raw response base64 block ONLY if BOTH start and end delimiters exist
    if grep -q "===AZURE_RAW_RESPONSE_BASE64_START===" "$CONTAINER_LOG_FILE" 2>/dev/null && grep -q "===AZURE_RAW_RESPONSE_BASE64_END===" "$CONTAINER_LOG_FILE" 2>/dev/null; then
      sed -n '/===AZURE_RAW_RESPONSE_BASE64_START===/,/===AZURE_RAW_RESPONSE_BASE64_END===/p' "$CONTAINER_LOG_FILE" \
        | grep -v "===AZURE_RAW_RESPONSE_BASE64" | tr -d '\r\n ' | base64 -d > "$RAW_RESPONSE_FILE" 2>/dev/null || true
    else
      rm -f "$RAW_RESPONSE_FILE"
    fi

    # Rigorous validation of JSON schema and raw bytes integrity
    if [ -s "$PROBE_RESULT_FILE" ]; then
      set +e
      python3 -c "
import sys, json, hashlib, os
with open('$PROBE_RESULT_FILE', 'r', encoding='utf-8') as f:
    data = json.load(f)
if data.get('probe_name') != 'AZURE_BOUNDED_PROBE_DIAGNOSTIC':
    sys.exit(2)
expected_sha = data.get('evidence', {}).get('raw_response_sha256')
expected_bytes = data.get('evidence', {}).get('raw_response_size_bytes', 0)
if expected_bytes > 0 or expected_sha:
    raw_path = '$RAW_RESPONSE_FILE'
    if not os.path.exists(raw_path):
        sys.exit(3)
    actual_bytes = os.path.getsize(raw_path)
    if actual_bytes != expected_bytes:
        sys.exit(4)
    with open(raw_path, 'rb') as rf:
        actual_sha = hashlib.sha256(rf.read()).hexdigest()
    if actual_sha != expected_sha:
        sys.exit(5)
sys.exit(0)
" 2>/dev/null
      VALID_STATUS=$?
      set -e

      if [ $VALID_STATUS -eq 0 ]; then
        EXPORT_VERIFIED=true
        echo "Evidence Export: VERIFIED (Preserved to: $PROBE_RESULT_FILE)"
      else
        EXPORT_VERIFIED=false
        echo "WARNING: Evidence validation failed with code $VALID_STATUS (JSON invalid or raw bytes mismatch)." >&2
      fi
    else
      EXPORT_VERIFIED=false
      echo "WARNING: Evidence export failed (delimited JSON missing in container logs)." >&2
    fi
  fi
}

cleanup() {
  ORIG_EXIT_CODE=$?
  echo "=== Running Guaranteed Teardown of Diagnostic Resources ==="

  # Step 0: Ensure evidence is preserved and validated before deleting container
  preserve_and_validate_evidence

  # Step 1: Explicitly delete ACI Container ONLY if created
  if [ "$ACI_CREATED" = true ]; then
    echo "1. Deleting ACI Container: $ACI_NAME..."
    az container delete --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --yes 2>/dev/null || true
  fi

  # Step 2: Explicitly delete Azure Container Registry ONLY if created
  if [ "$ACR_CREATED" = true ]; then
    echo "2. Deleting Azure Container Registry: $ACR_NAME..."
    az acr delete --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --yes 2>/dev/null || true
  fi

  # Step 3: Delete Ephemeral Resource Group ONLY if created by this invocation
  if [ "$RG_CREATED" = true ]; then
    echo "3. Deleting Dedicated Ephemeral Resource Group: $RESOURCE_GROUP..."
    az group delete --name "$RESOURCE_GROUP" --yes 2>/dev/null || true
  fi

  # Step 4: Complete Absence Verification without treating errors as absence
  echo "4. Verifying Absence of Created Resources..."
  ALL_REMOVED=true

  if [ "$ACI_CREATED" = true ]; then
    ACI_GONE=false
    for i in {1..20}; do
      set +e
      ACI_OUT=$(az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" 2>&1)
      ACI_STATUS=$?
      set -e
      if [[ "$ACI_OUT" == *"ResourceNotFound"* ]] || [[ "$ACI_OUT" == *"ResourceGroupNotFound"* ]] || [[ "$ACI_OUT" == *"could not be found"* ]]; then
        ACI_GONE=true
        break
      fi
      sleep 3
    done
    if [ "$ACI_GONE" != true ]; then
      echo "ERROR: ACI container $ACI_NAME could not be verified deleted!" >&2
      ALL_REMOVED=false
    fi
  fi

  if [ "$ACR_CREATED" = true ]; then
    ACR_GONE=false
    for i in {1..20}; do
      set +e
      ACR_OUT=$(az acr show --name "$ACR_NAME" 2>&1)
      ACR_STATUS=$?
      set -e
      if [[ "$ACR_OUT" == *"ResourceNotFound"* ]] || [[ "$ACR_OUT" == *"could not be found"* ]]; then
        ACR_GONE=true
        break
      fi
      sleep 3
    done
    if [ "$ACR_GONE" != true ]; then
      echo "ERROR: ACR registry $ACR_NAME could not be verified deleted!" >&2
      ALL_REMOVED=false
    fi
  fi

  if [ "$RG_CREATED" = true ]; then
    RG_GONE=false
    for i in {1..25}; do
      set +e
      RG_OUT=$(az group exists --name "$RESOURCE_GROUP" 2>/dev/null)
      RG_CHECK_STATUS=$?
      set -e
      RG_OUT_CLEAN=$(echo "$RG_OUT" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
      if [ $RG_CHECK_STATUS -eq 0 ] && [ "$RG_OUT_CLEAN" = "false" ]; then
        RG_GONE=true
        break
      fi
      sleep 3
    done
    if [ "$RG_GONE" != true ]; then
      echo "ERROR: Ephemeral Resource Group $RESOURCE_GROUP could not be verified deleted!" >&2
      ALL_REMOVED=false
    fi
  fi

  # Determine probe execution outcome
  PROBE_STATUS_VAL="UNKNOWN"
  if [ -s "$PROBE_RESULT_FILE" ]; then
    PROBE_STATUS_VAL=$(python3 -c "import json; print(json.load(open('$PROBE_RESULT_FILE')).get('overall_status', 'UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
  fi

  if [ "$CONTAINER_EXIT_CODE" -eq 0 ] && [[ "$PROBE_STATUS_VAL" == "SUCCESS_PROBE_COMPLETE" || "$PROBE_STATUS_VAL" == "SUCCESS_CONNECTIVITY_ONLY" ]]; then
    PROBE_SUCCESS=true
  else
    PROBE_SUCCESS=false
  fi

  echo "===================================================================================="
  echo "DEPLOYMENT EXECUTION REPORT:"
  echo "  - Resources Created by Invocation: ACI=$ACI_CREATED, ACR=$ACR_CREATED, RG=$RG_CREATED"
  echo "  - Stage 1 [Probe Execution]: $([ "$PROBE_SUCCESS" = true ] && echo "SUCCESS ($PROBE_STATUS_VAL)" || echo "FAILED ($PROBE_STATUS_VAL)")"
  echo "  - Stage 2 [Evidence Export]: $([ "$EXPORT_VERIFIED" = true ] && echo "VERIFIED" || echo "FAILED")"
  echo "  - Stage 3 [Resource Teardown]: $([ "$ALL_REMOVED" = true ] && echo "VERIFIED (\$0.00 lingering cost)" || echo "UNRESOLVED")"
  echo "===================================================================================="

  # Propagate failure if ANY stage failed
  if [ "$PROBE_SUCCESS" != true ] || [ "$EXPORT_VERIFIED" != true ] || [ "$ALL_REMOVED" != true ]; then
    exit 1
  fi
}

trap cleanup EXIT

echo "=== 1. Creating Ephemeral Resource Group: $RESOURCE_GROUP ($LOCATION) ==="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
RG_CREATED=true

echo "=== 2. Creating Ephemeral Azure Container Registry: $ACR_NAME ==="
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true
ACR_CREATED=true

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
  --command-line "python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP --max-requests 3 --max-retries 1 --run-deadline-seconds 60.0" \
  --environment-variables \
      MARIANOS_PROXY_URL="$MARIANOS_PROXY_URL"
ACI_CREATED=true

echo "=== 5. Following Container Execution and Streaming Logs ==="
set +e
az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --follow | tee "$CONTAINER_LOG_FILE"
STREAM_EXIT_CODE=$?
set -e

# Query container instance exit code if available
ACI_RUN_EXIT_CODE=$(az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --query "containers[0].instanceView.currentState.exitCode" --output tsv 2>/dev/null || echo "")
if [ -n "$ACI_RUN_EXIT_CODE" ]; then
  CONTAINER_EXIT_CODE=$ACI_RUN_EXIT_CODE
else
  CONTAINER_EXIT_CODE=$STREAM_EXIT_CODE
fi
