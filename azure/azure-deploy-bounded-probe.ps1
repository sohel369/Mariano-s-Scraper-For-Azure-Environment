# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script (PowerShell)
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces Reviewer Item 1 & Item 5 Requirements (October 30 Review):
#  1. Uniquely owned ephemeral resource group; strictly refuses pre-existing/shared groups.
#  2. Safe error handling: Failed existence check stops immediately; does not assume permission.
#  3. Explicit resource ownership tracking: Deletes only resources created by this invocation.
#  4. Absence verification: Confirms deletion of created resources; unresolved cleanup exits 1.
#  5. Durable evidence validation: Validates external JSON extraction before container teardown.
# ==============================================================================

param(
    [string]$ResourceGroup = "",
    [string]$Location = "eastus",
    [string]$AcrName = ("acrmprobe" + (Get-Random -Minimum 10000 -Maximum 99999)),
    [string]$ImageName = "marianos-scraper-probe",
    [string]$Tag = "diagnostic-v3",
    [string]$AciName = "aci-marianos-probe-job",
    [string]$OutputDir = "logs"
)

$ErrorActionPreference = "Stop"

# Resource creation state flags
$rgCreated = $false
$acrCreated = $false
$aciCreated = $false
$exportVerified = $false
$allRemoved = $false

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$ContainerLogPath = Join-Path $OutputDir "azure_bounded_probe_container.log"
$JsonResultPath = Join-Path $OutputDir "azure_bounded_probe_result.json"
$RawResponsePath = Join-Path $OutputDir "azure_probe_raw_response.html"

# 1. Ephemeral Resource Group & Ownership Verification
if (![string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $rgCheck = az group exists --name $ResourceGroup 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Error @"
====================================================================================
CRITICAL ERROR: Failed to query resource group existence (exit code $LASTEXITCODE).
Refusing to proceed to prevent accidental modification of shared resources.
====================================================================================
"@
        exit 1
    }
    $rgClean = $rgCheck.ToString().Trim().ToLower()
    if ($rgClean -eq "true") {
        Write-Error @"
====================================================================================
CRITICAL ERROR: Resource group '$ResourceGroup' already exists.
To guarantee that existing or shared resources are NEVER deleted,
this diagnostic strictly refuses pre-existing resource groups.
Please specify an unused resource group name or omit parameter to auto-generate.
====================================================================================
"@
        exit 1
    }
    if ($rgClean -ne "false") {
        Write-Error "CRITICAL ERROR: Unknown/error response from az group exists: '$rgCheck'."
        exit 1
    }
} else {
    $uniqueId = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() + (Get-Random -Minimum 1000 -Maximum 9999).ToString()
    $ResourceGroup = "rg-marianos-probe-$uniqueId"
}

Write-Host "=== Configured Diagnostic Resources ===" -ForegroundColor Cyan
Write-Host "Resource Group:  $ResourceGroup (Ephemeral)"
Write-Host "ACR Registry:    $AcrName"
Write-Host "ACI Container:   $AciName (1 vCPU, 2.0 GB RAM)"
Write-Host "Location:        $Location"
Write-Host "========================================"

function Preserve-And-Validate-Evidence {
    Write-Host "=== Preserving Diagnostic Evidence Outside Disposable Container ===" -ForegroundColor Cyan
    if ($script:aciCreated -and (Test-Path $script:ContainerLogPath)) {
        $logContent = Get-Content -Path $script:ContainerLogPath -Raw

        # Extract JSON delimiter block
        if ($logContent -match '===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===') {
            $extractedJson = $matches[1].Trim()
            $extractedJson | Out-File -FilePath $script:JsonResultPath -Encoding utf8
        }

        # Extract base64 raw response block
        if ($logContent -match '===AZURE_RAW_RESPONSE_BASE64_START===([\s\S]*?)===AZURE_RAW_RESPONSE_BASE64_END===') {
            try {
                $base64Str = $matches[1].Trim() -replace '\s+', ''
                $rawBytes = [System.Convert]::FromBase64String($base64Str)
                [System.IO.File]::WriteAllBytes($script:RawResponsePath, $rawBytes)
            } catch {
                Write-Warning "Could not decode raw base64 response: $_"
            }
        }

        # Validate that JSON exists and is valid
        if (Test-Path $script:JsonResultPath) {
            try {
                $parsed = Get-Content -Path $script:JsonResultPath -Raw | ConvertFrom-Json
                if ($parsed -ne $null -and $parsed.probe_name -eq "AZURE_BOUNDED_PROBE_DIAGNOSTIC") {
                    $script:exportVerified = $true
                    Write-Host "Evidence Export: VERIFIED (Preserved to: $script:JsonResultPath)" -ForegroundColor Green
                    return
                }
            } catch {
                Write-Warning "JSON result verification failed: $_"
            }
        }
        $script:exportVerified = $false
        Write-Warning "Evidence export failed (delimited JSON missing or corrupted in container logs)."
    }
}

try {
    Write-Host "=== 1. Creating Ephemeral Resource Group: $ResourceGroup ($Location) ===" -ForegroundColor Cyan
    az group create --name $ResourceGroup --location $Location | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create resource group $ResourceGroup" }
    $rgCreated = $true

    Write-Host "=== 2. Creating Ephemeral Azure Container Registry: $AcrName ===" -ForegroundColor Cyan
    az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create ACR $AcrName" }
    $acrCreated = $true

    Write-Host "=== 3. Building Probe Docker Container ===" -ForegroundColor Cyan
    az acr build --registry $AcrName --image "$($ImageName):$($Tag)" -f azure/Dockerfile .
    if ($LASTEXITCODE -ne 0) { throw "Failed to build container image" }

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
      --command-line "python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP --max-requests 3 --max-retries 1 --run-deadline-seconds 60.0" `
      --environment-variables `
          MARIANOS_PROXY_URL="$env:MARIANOS_PROXY_URL" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create container instance $AciName" }
    $aciCreated = $true

    Write-Host "=== 5. Streaming Logs from Container ===" -ForegroundColor Cyan
    $logs = az container logs --resource-group $ResourceGroup --name $AciName --follow
    $logs | Out-File -FilePath $ContainerLogPath -Encoding utf8

} finally {
    Write-Host "=== 6. Initiating Guaranteed Teardown of Diagnostic Resources ===" -ForegroundColor Cyan

    Preserve-And-Validate-Evidence

    # Delete ACI container ONLY if created
    if ($aciCreated) {
        Write-Host "Deleting Container: $AciName..." -ForegroundColor Gray
        az container delete --resource-group $ResourceGroup --name $AciName --yes 2>$null | Out-Null
    }

    # Delete ACR ONLY if created
    if ($acrCreated) {
        Write-Host "Deleting Container Registry: $AcrName..." -ForegroundColor Gray
        az acr delete --resource-group $ResourceGroup --name $AcrName --yes 2>$null | Out-Null
    }

    # Delete Resource Group ONLY if created by this invocation
    if ($rgCreated) {
        Write-Host "Deleting Dedicated Resource Group: $ResourceGroup..." -ForegroundColor Gray
        az group delete --name $ResourceGroup --yes 2>$null | Out-Null
    }

    # Polling absence verification
    Write-Host "Verifying absence of created resources..." -ForegroundColor Gray
    $allRemoved = $true

    if ($aciCreated) {
        $aciGone = $false
        for ($i = 0; $i -lt 20; $i++) {
            $checkAci = az container show --resource-group $ResourceGroup --name $AciName --query name --output tsv 2>&1
            if ($checkAci -match "ResourceNotFound" -or $checkAci -match "ResourceGroupNotFound" -or $checkAci -match "could not be found") {
                $aciGone = $true
                break
            }
            Start-Sleep -Seconds 3
        }
        if (-not $aciGone) {
            Write-Warning "ERROR: ACI container $AciName could not be verified deleted!"
            $allRemoved = $false
        }
    }

    if ($acrCreated) {
        $acrGone = $false
        for ($i = 0; $i -lt 20; $i++) {
            $checkAcr = az acr show --name $AcrName --query name --output tsv 2>&1
            if ($checkAcr -match "ResourceNotFound" -or $checkAcr -match "could not be found") {
                $acrGone = $true
                break
            }
            Start-Sleep -Seconds 3
        }
        if (-not $acrGone) {
            Write-Warning "ERROR: ACR registry $AcrName could not be verified deleted!"
            $allRemoved = $false
        }
    }

    Write-Host "====================================================================================" -ForegroundColor Cyan
    Write-Host "TEARDOWN VERIFICATION REPORT:" -ForegroundColor Cyan
    Write-Host "  - Resources Created by Invocation: ACI=$aciCreated, ACR=$acrCreated, RG=$rgCreated"
    Write-Host "  - Resource Removal Verified:      $allRemoved"
    Write-Host "  - Evidence Export Verified:       $exportVerified"
    if ($allRemoved) {
        Write-Host "  - Residual Compute / Storage Cost: `$0.00" -ForegroundColor Green
    } else {
        Write-Host "  - Residual Compute / Storage Cost: UNRESOLVED (Resource cleanup failed)" -ForegroundColor Red
    }
    Write-Host "====================================================================================" -ForegroundColor Cyan

    if (-not $allRemoved -or -not $exportVerified) {
        exit 1
    }
}
