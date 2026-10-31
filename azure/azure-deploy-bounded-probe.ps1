# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script (PowerShell)
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
$probeSuccess = $false
$exportVerified = $false
$allRemoved = $false
$containerExitCode = 1

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$ContainerLogPath = Join-Path $OutputDir "azure_bounded_probe_container.log"
$JsonResultPath = Join-Path $OutputDir "azure_bounded_probe_result.json"
$RawResponsePath = Join-Path $OutputDir "azure_probe_raw_response.html"

# Pre-execution cleanup: Strictly remove stale result files to prevent false verification from previous runs
Remove-Item -Path $ContainerLogPath, $JsonResultPath, $RawResponsePath -Force -ErrorAction SilentlyContinue

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
    if ($script:aciCreated) {
        # Bounded recovery path: If log file does not exist or delimiters missing, retry fetching logs
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            if (-not (Test-Path $script:ContainerLogPath) -or -not (Select-String -Path $script:ContainerLogPath -Pattern "===AZURE_PROBE_JSON_START===" -Quiet -ErrorAction SilentlyContinue)) {
                Write-Host "Fetching container logs from Azure (attempt $attempt/3)..."
                az container logs --resource-group $ResourceGroup --name $AciName 2>$null | Out-File -FilePath $script:ContainerLogPath -Encoding utf8
            }
            if ((Select-String -Path $script:ContainerLogPath -Pattern "===AZURE_PROBE_JSON_START===" -Quiet -ErrorAction SilentlyContinue) -and
                (Select-String -Path $script:ContainerLogPath -Pattern "===AZURE_PROBE_JSON_END===" -Quiet -ErrorAction SilentlyContinue)) {
                break
            }
            Start-Sleep -Seconds 2
        }

        if (Test-Path $script:ContainerLogPath) {
            $logContent = Get-Content -Path $script:ContainerLogPath -Raw

            # Extract JSON delimiter block ONLY if BOTH start and end delimiters exist
            if ($logContent -match '===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===') {
                $extractedJson = $matches[1].Trim()
                $extractedJson | Out-File -FilePath $script:JsonResultPath -Encoding utf8
            } else {
                Write-Warning "Incomplete or missing JSON delimiters in container log."
                Remove-Item -Path $script:JsonResultPath -Force -ErrorAction SilentlyContinue
            }

            # Extract base64 raw response block ONLY if BOTH start and end delimiters exist
            if ($logContent -match '===AZURE_RAW_RESPONSE_BASE64_START===([\s\S]*?)===AZURE_RAW_RESPONSE_BASE64_END===') {
                try {
                    $base64Str = $matches[1].Trim() -replace '\s+', ''
                    $rawBytes = [System.Convert]::FromBase64String($base64Str)
                    [System.IO.File]::WriteAllBytes($script:RawResponsePath, $rawBytes)
                } catch {
                    Write-Warning "Could not decode raw base64 response: $_"
                    Remove-Item -Path $script:RawResponsePath -Force -ErrorAction SilentlyContinue
                }
            } else {
                Remove-Item -Path $script:RawResponsePath -Force -ErrorAction SilentlyContinue
            }
        }

        # Rigorous validation of JSON schema and raw bytes integrity
        if (Test-Path $script:JsonResultPath) {
            try {
                $parsed = Get-Content -Path $script:JsonResultPath -Raw | ConvertFrom-Json
                if ($parsed -ne $null -and $parsed.probe_name -eq "AZURE_BOUNDED_PROBE_DIAGNOSTIC") {
                    $expectedBytes = [int]($parsed.evidence.raw_response_size_bytes)
                    $expectedSha = [string]($parsed.evidence.raw_response_sha256)

                    $rawValid = $true
                    if ($expectedBytes -gt 0 -or !([string]::IsNullOrWhiteSpace($expectedSha))) {
                        if (-not (Test-Path $script:RawResponsePath)) {
                            $rawValid = $false
                            Write-Warning "Raw response file missing on host."
                        } else {
                            $actualBytes = (Get-Item $script:RawResponsePath).Length
                            if ($actualBytes -ne $expectedBytes) {
                                $rawValid = $false
                                Write-Warning "Raw byte count mismatch: $actualBytes vs expected $expectedBytes"
                            }
                            $sha = [System.Security.Cryptography.SHA256]::Create()
                            $fileBytes = [System.IO.File]::ReadAllBytes($script:RawResponsePath)
                            $hashBytes = $sha.ComputeHash($fileBytes)
                            $actualSha = (-join ($hashBytes | ForEach-Object { "{0:x2}" -f $_ }))
                            if ($actualSha -ne $expectedSha) {
                                $rawValid = $false
                                Write-Warning "Raw SHA-256 mismatch: $actualSha vs expected $expectedSha"
                            }
                        }
                    }

                    if ($rawValid) {
                        $script:exportVerified = $true
                        Write-Host "Evidence Export: VERIFIED (Preserved to: $script:JsonResultPath)" -ForegroundColor Green
                        return
                    }
                }
            } catch {
                Write-Warning "JSON result verification failed: $_"
            }
        }
        $script:exportVerified = $false
        Write-Warning "Evidence export failed (delimited JSON missing, corrupted, or raw response mismatch)."
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

    $aciExitCode = az container show --resource-group $ResourceGroup --name $AciName --query "containers[0].instanceView.currentState.exitCode" --output tsv 2>$null
    if ($aciExitCode -ne $null -and $aciExitCode -ne "") {
        $containerExitCode = [int]$aciExitCode
    } else {
        $containerExitCode = $LASTEXITCODE
    }

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

    # Complete absence verification
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

    if ($rgCreated) {
        $rgGone = $false
        for ($i = 0; $i -lt 25; $i++) {
            $checkRg = az group exists --name $ResourceGroup 2>$null
            if ($LASTEXITCODE -eq 0 -and $checkRg.ToString().Trim().ToLower() -eq "false") {
                $rgGone = $true
                break
            }
            Start-Sleep -Seconds 3
        }
        if (-not $rgGone) {
            Write-Warning "ERROR: Ephemeral Resource Group $ResourceGroup could not be verified deleted!"
            $allRemoved = $false
        }
    }

    $probeStatusVal = "UNKNOWN"
    if (Test-Path $JsonResultPath) {
        try {
            $parsedJson = Get-Content -Path $JsonResultPath -Raw | ConvertFrom-Json
            $probeStatusVal = $parsedJson.overall_status
        } catch {}
    }

    if (($containerExitCode -eq 0) -and ($probeStatusVal -eq "SUCCESS_PROBE_COMPLETE" -or $probeStatusVal -eq "SUCCESS_CONNECTIVITY_ONLY")) {
        $probeSuccess = $true
    } else {
        $probeSuccess = $false
    }

    Write-Host "====================================================================================" -ForegroundColor Cyan
    Write-Host "DEPLOYMENT EXECUTION REPORT:" -ForegroundColor Cyan
    Write-Host "  - Resources Created by Invocation: ACI=$aciCreated, ACR=$acrCreated, RG=$rgCreated"
    Write-Host "  - Stage 1 [Probe Execution]: $(if ($probeSuccess) { "SUCCESS ($probeStatusVal)" } else { "FAILED ($probeStatusVal)" })"
    Write-Host "  - Stage 2 [Evidence Export]: $(if ($exportVerified) { "VERIFIED" } else { "FAILED" })"
    Write-Host "  - Stage 3 [Resource Teardown]: $(if ($allRemoved) { "VERIFIED (`$0.00 lingering cost)" } else { "UNRESOLVED" })"
    Write-Host "====================================================================================" -ForegroundColor Cyan

    if (-not $probeSuccess -or -not $exportVerified -or -not $allRemoved) {
        exit 1
    }
}
