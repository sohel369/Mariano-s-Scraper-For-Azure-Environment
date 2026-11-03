#!/bin/bash
set -eo pipefail

# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces Reviewer Requirements (November 1 Review):
#  1. Uniquely owned ephemeral resource group; strictly refuses pre-existing/shared groups.
#  2. Safe error handling: Failed existence check stops immediately; does not assume permission.
#  3. Explicit resource ownership tracking: Deletes only resources created by this invocation.
#  4. Complete absence verification: Confirms deletion of ACI, ACR, AND Resource Group.
#  5. Durable evidence validation: Run ID & commit binding, strict start/end delimiters,
#     complete log-recovery retry for truncated blocks, SHA-256 and byte-count integrity check.
#  6. Stage-separated reporting: Reports Probe Execution, Evidence Export, and Resource Teardown,
#     exiting non-zero if ANY stage fails.
#  7. Bounded execution: Timeouts on CLI calls; terminal container exit code strictly required
#     without falling back to log-streaming command exit status.
# ==============================================================================

# Execution and resource state flags
RG_CREATED=false
ACR_CREATED=false
ACI_CREATED=false
PROBE_SUCCESS=false
EXPORT_VERIFIED=false
ALL_REMOVED=false
CONTAINER_EXIT_CODE="UNKNOWN"

SUPPLIED_RG="$1"
LOCATION="${2:-eastus}"
OUTPUT_DIR="${OUTPUT_DIR:-logs}"
if [ -n "${3:-}" ]; then
  OUTPUT_DIR="$3"
fi
RUN_ID="$(date +%Y%m%d_%H%M%S)_$((RANDOM % 9000 + 1000))"
PROBE_RESULT_FILE="$OUTPUT_DIR/azure_bounded_probe_result.json"
RAW_RESPONSE_FILE="$OUTPUT_DIR/azure_probe_raw_response.html"
CONTAINER_LOG_FILE="$OUTPUT_DIR/azure_bounded_probe_container.log"

mkdir -p "$OUTPUT_DIR"

# Pre-execution cleanup: Strictly remove stale result files to prevent false verification from previous runs
rm -f "$PROBE_RESULT_FILE" "$RAW_RESPONSE_FILE" "$CONTAINER_LOG_FILE"

# Resolve pinned git commit hash
PINNED_COMMIT=$(git rev-parse HEAD 2>/dev/null || cat logs/git_commit_lineage_proof.json 2>/dev/null | grep -o '"head_commit": "[^"]*' | cut -d'"' -f4 || echo "")

# Preflight: Verify required timeout utility and commit hash
if ! command -v timeout >/dev/null 2>&1; then
  echo "====================================================================================" >&2
  echo "CRITICAL PREFLIGHT ERROR: 'timeout' (GNU coreutils) utility is required for bounded execution." >&2
  echo "====================================================================================" >&2
  exit 1
fi

if [ -z "$PINNED_COMMIT" ]; then
  echo "====================================================================================" >&2
  echo "CRITICAL PREFLIGHT ERROR: Pinned git commit could not be determined." >&2
  echo "Bounded execution requires an authoritative non-empty commit hash for provenance." >&2
  echo "====================================================================================" >&2
  exit 1
fi

# Resolve working Python 3 interpreter (prefers python3 on Linux, py -3 or python on Windows)
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys' >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v py >/dev/null 2>&1 && py -3 -c 'import sys' >/dev/null 2>&1; then
  PYTHON_CMD="py -3"
elif command -v python >/dev/null 2>&1 && python -c 'import sys' >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "CRITICAL PREFLIGHT ERROR: Working Python 3 interpreter is required for validation." >&2
  exit 1
fi

# Helper: Run command with timeout and guaranteed SIGKILL escalation
run_with_timeout() {
  local timeout_sec="$1"
  shift
  timeout --kill-after=5s "$timeout_sec" "$@"
}

# 1. Ephemeral Resource Group & Ownership Verification
if [ -n "$SUPPLIED_RG" ]; then
  # Explicit absence check with strict exit-code handling
  set +e
  RG_EXISTS=$(run_with_timeout 30 az group exists --name "$SUPPLIED_RG" 2>/dev/null)
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
echo "Pinned Commit:   $PINNED_COMMIT"
echo "Resource Group:  $RESOURCE_GROUP (Ephemeral)"
echo "ACR Registry:    $ACR_NAME"
echo "ACI Container:   $ACI_NAME (1 vCPU, 2.0 GB RAM)"
echo "Location:        $LOCATION"
echo "========================================"

# Evidence completeness validation helper
check_evidence_complete() {
  local log_file="$1"
  local target_run_id="$2"
  local target_commit="$3"
  if [ ! -f "$log_file" ] || [ ! -s "$log_file" ]; then
    return 1
  fi
  $PYTHON_CMD -c "
import sys, re, json

log_path = sys.argv[1]
target_run_id = sys.argv[2]
target_commit = sys.argv[3]

try:
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
except Exception:
    sys.exit(1)

# Check for both JSON START and END
json_matches = re.findall(r'===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===', content)
if not json_matches:
    sys.exit(2) # Incomplete or missing JSON delimiters

# Parse last JSON block
try:
    data = json.loads(json_matches[-1].strip())
except Exception:
    sys.exit(3) # Malformed JSON

# Verify run_id and pinned_git_commit strictly
if not target_run_id or data.get('run_id') != target_run_id:
    sys.exit(4) # Run ID mismatch or missing
if not target_commit or not data.get('pinned_git_commit') or data.get('pinned_git_commit') != target_commit:
    sys.exit(5) # Commit mismatch or missing

# Check raw response delimiters if raw body is expected
raw_bytes = data.get('evidence', {}).get('raw_response_size_bytes', 0)
raw_sha = data.get('evidence', {}).get('raw_response_sha256')
if raw_bytes > 0 or raw_sha:
    raw_matches = re.findall(r'===AZURE_RAW_RESPONSE_BASE64_START===([\s\S]*?)===AZURE_RAW_RESPONSE_BASE64_END===', content)
    if not raw_matches:
        sys.exit(6) # Incomplete or missing raw body delimiters

sys.exit(0)
" "$log_file" "$target_run_id" "$target_commit" 2>/dev/null
}

# Evidence Extraction & Validation Helper (Runs before resource teardown)
preserve_and_validate_evidence() {
  echo "=== Preserving Diagnostic Evidence Outside Disposable Container ==="
  if [ "$ACI_CREATED" = true ]; then
    # Bounded recovery path: Retries fetching logs if delimiters or payload are incomplete
    for attempt in 1 2 3 4 5; do
      if ! check_evidence_complete "$CONTAINER_LOG_FILE" "$RUN_ID" "$PINNED_COMMIT"; then
        echo "Evidence incomplete in log; retrieving fresh container logs from Azure (attempt $attempt/5)..."
        run_with_timeout 30 az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" > "$CONTAINER_LOG_FILE" 2>/dev/null || true
      fi
      if check_evidence_complete "$CONTAINER_LOG_FILE" "$RUN_ID" "$PINNED_COMMIT"; then
        echo "Complete delimited evidence confirmed in container log."
        break
      fi
      sleep 2
    done

    # Extract the authoritative LAST delimited blocks
    $PYTHON_CMD -c "
import re, json, base64, sys

log_file = sys.argv[1]
result_file = sys.argv[2]
raw_file = sys.argv[3]

try:
    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
except Exception:
    sys.exit(1)

# Extract terminal JSON block
json_matches = re.findall(r'===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===', content)
if json_matches:
    last_json = json_matches[-1].strip()
    with open(result_file, 'w', encoding='utf-8') as pf:
        pf.write(last_json)
else:
    sys.exit(2)

# Extract terminal raw response block if present
raw_matches = re.findall(r'===AZURE_RAW_RESPONSE_BASE64_START===([\s\S]*?)===AZURE_RAW_RESPONSE_BASE64_END===', content)
if raw_matches:
    raw_b64 = re.sub(r'\s+', '', raw_matches[-1])
    try:
        raw_bytes = base64.b64decode(raw_b64)
        with open(raw_file, 'wb') as rf:
            rf.write(raw_bytes)
    except Exception:
        pass
" "$CONTAINER_LOG_FILE" "$PROBE_RESULT_FILE" "$RAW_RESPONSE_FILE" 2>/dev/null || true

    # Rigorous validation of JSON schema, version identity, and raw bytes integrity
    if [ -s "$PROBE_RESULT_FILE" ]; then
      set +e
      $PYTHON_CMD -c "
import sys, json, hashlib, os

result_file = sys.argv[1]
expected_run_id = sys.argv[2]
expected_commit = sys.argv[3]
raw_path = sys.argv[4]

with open(result_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

if data.get('probe_name') != 'AZURE_BOUNDED_PROBE_DIAGNOSTIC':
    sys.exit(2)
if not expected_run_id or data.get('run_id') != expected_run_id:
    sys.exit(3)
if not expected_commit or not data.get('pinned_git_commit') or data.get('pinned_git_commit') != expected_commit:
    sys.exit(7)

expected_sha = data.get('evidence', {}).get('raw_response_sha256')
expected_bytes = data.get('evidence', {}).get('raw_response_size_bytes', 0)
if expected_bytes > 0 or expected_sha:
    if not os.path.exists(raw_path):
        sys.exit(4)
    actual_bytes = os.path.getsize(raw_path)
    if actual_bytes != expected_bytes:
        sys.exit(5)
    with open(raw_path, 'rb') as rf:
        actual_sha = hashlib.sha256(rf.read()).hexdigest()
    if actual_sha != expected_sha:
        sys.exit(6)
sys.exit(0)
" "$PROBE_RESULT_FILE" "$RUN_ID" "$PINNED_COMMIT" "$RAW_RESPONSE_FILE" 2>/dev/null
      VALID_STATUS=$?
      set -e

      if [ $VALID_STATUS -eq 0 ]; then
        EXPORT_VERIFIED=true
        echo "Evidence Export: VERIFIED (Preserved to: $PROBE_RESULT_FILE)"
      else
        EXPORT_VERIFIED=false
        echo "WARNING: Evidence validation failed with code $VALID_STATUS (JSON invalid, version mismatch, or raw bytes error)." >&2
      fi
    else
      EXPORT_VERIFIED=false
      echo "WARNING: Evidence export failed (delimited JSON missing in container logs)." >&2
    fi

    # Preserve recoverable diagnostic copies before container teardown
    if [ "$EXPORT_VERIFIED" != true ]; then
      echo "Export unverified; preserving recoverable container artifacts before teardown..."
      cp "$CONTAINER_LOG_FILE" "$OUTPUT_DIR/unverified_container_${RUN_ID}.log" 2>/dev/null || true
      run_with_timeout 30 az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" > "$OUTPUT_DIR/unverified_container_state_${RUN_ID}.json" 2>/dev/null || true
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
    run_with_timeout 60 az container delete --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --yes 2>/dev/null || true
  fi

  # Step 2: Explicitly delete Azure Container Registry ONLY if created
  if [ "$ACR_CREATED" = true ]; then
    echo "2. Deleting Azure Container Registry: $ACR_NAME..."
    run_with_timeout 60 az acr delete --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --yes 2>/dev/null || true
  fi

  # Step 3: Delete Ephemeral Resource Group ONLY if created by this invocation
  if [ "$RG_CREATED" = true ]; then
    echo "3. Deleting Dedicated Ephemeral Resource Group: $RESOURCE_GROUP..."
    run_with_timeout 90 az group delete --name "$RESOURCE_GROUP" --yes 2>/dev/null || true
  fi

  # Step 4: Complete Absence Verification without treating errors as absence
  echo "4. Verifying Absence of Created Resources..."
  ALL_REMOVED=true

  if [ "$ACI_CREATED" = true ]; then
    ACI_GONE=false
    for i in {1..20}; do
      set +e
      ACI_OUT=$(run_with_timeout 30 az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" 2>&1)
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
      ACR_OUT=$(run_with_timeout 30 az acr show --name "$ACR_NAME" 2>&1)
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
      RG_OUT=$(run_with_timeout 30 az group exists --name "$RESOURCE_GROUP" 2>/dev/null)
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

  # Determine probe execution outcome strictly
  PROBE_STATUS_VAL="UNKNOWN"
  if [ -s "$PROBE_RESULT_FILE" ]; then
    PROBE_STATUS_VAL=$($PYTHON_CMD -c "import sys, json; print(json.load(open(sys.argv[1])).get('overall_status', 'UNKNOWN'))" "$PROBE_RESULT_FILE" 2>/dev/null || echo "UNKNOWN")
  fi

  # Strictly require container exit code 0; unknown or missing exit code fails closed
  if [ "$CONTAINER_EXIT_CODE" = "0" ] && [[ "$PROBE_STATUS_VAL" == "SUCCESS_PROBE_COMPLETE" || "$PROBE_STATUS_VAL" == "SUCCESS_CONNECTIVITY_ONLY" ]]; then
    PROBE_SUCCESS=true
  else
    PROBE_SUCCESS=false
  fi

  echo "===================================================================================="
  echo "DEPLOYMENT EXECUTION REPORT:"
  echo "  - Resources Created by Invocation: ACI=$ACI_CREATED, ACR=$ACR_CREATED, RG=$RG_CREATED"
  echo "  - Stage 1 [Probe Execution]: $([ "$PROBE_SUCCESS" = true ] && echo "SUCCESS ($PROBE_STATUS_VAL, Exit 0)" || echo "FAILED ($PROBE_STATUS_VAL, Exit $CONTAINER_EXIT_CODE)")"
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
run_with_timeout 60 az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
RG_CREATED=true

echo "=== 2. Creating Ephemeral Azure Container Registry: $ACR_NAME ==="
run_with_timeout 60 az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true
ACR_CREATED=true

echo "=== 3. Building Probe Docker Container ==="
run_with_timeout 180 az acr build --registry "$ACR_NAME" --image "$IMAGE_NAME:$TAG" -f azure/Dockerfile .

ACR_LOGIN_SERVER=$(run_with_timeout 30 az acr show --name "$ACR_NAME" --query loginServer --output tsv)
ACR_PASSWORD=$(run_with_timeout 30 az acr credential show --name "$ACR_NAME" --query "passwords[0].value" --output tsv)
ACR_USERNAME=$(run_with_timeout 30 az acr credential show --name "$ACR_NAME" --query username --output tsv)

echo "=== 4. Executing Manual Bounded Probe in ACI (1 vCPU, 2.0 GB RAM) ==="
run_with_timeout 60 az container create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACI_NAME" \
  --image "$ACR_LOGIN_SERVER/$IMAGE_NAME:$TAG" \
  --registry-login-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --cpu 1 \
  --memory 2 \
  --restart-policy Never \
  --command-line "python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP --max-requests 3 --max-retries 1 --run-deadline-seconds 60.0 --run-id '$RUN_ID'" \
  --environment-variables \
      MARIANOS_PROXY_URL="$MARIANOS_PROXY_URL"
ACI_CREATED=true

echo "=== 5. Following Container Execution and Streaming Logs ==="
set +e
run_with_timeout 90 az container logs --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --follow | tee "$CONTAINER_LOG_FILE"
STREAM_EXIT_CODE=$?
set -e

# Query container terminal exit code strictly with bounded polling
CONTAINER_TERMINAL_EXIT=""
for poll in {1..15}; do
  ACI_STATE=$(run_with_timeout 20 az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --query "containers[0].instanceView.currentState.state" --output tsv 2>/dev/null || echo "")
  if [[ "$ACI_STATE" == "Terminated" || "$ACI_STATE" == "Failed" || "$ACI_STATE" == "Succeeded" ]]; then
    CONTAINER_TERMINAL_EXIT=$(run_with_timeout 20 az container show --resource-group "$RESOURCE_GROUP" --name "$ACI_NAME" --query "containers[0].instanceView.currentState.exitCode" --output tsv 2>/dev/null || echo "")
    break
  fi
  sleep 2
done

if [[ "$CONTAINER_TERMINAL_EXIT" =~ ^[0-9]+$ ]]; then
  CONTAINER_EXIT_CODE="$CONTAINER_TERMINAL_EXIT"
else
  echo "WARNING: Authoritative terminal exit code unavailable for container $ACI_NAME (State: $ACI_STATE)." >&2
  CONTAINER_EXIT_CODE="UNKNOWN"
fi
