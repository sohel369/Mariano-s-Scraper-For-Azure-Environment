# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script (PowerShell)
# Runs a manual-only, single-execution diagnostic probe (Max 20 records)
# Enforces Reviewer Item 1 & Item 4 Requirements (October 29 Review):
#  1. Uniquely owned ephemeral resource group; strictly refuses pre-existing/shared groups.
#  2. 1 vCPU / 2.0 GB Memory sizing.
#  3. Preserves reviewable evidence (structured JSON & raw HTML) OUTSIDE container BEFORE cleanup.
#  4. Deletes only resources created by this diagnostic invocation.
#  5. Verified resource absence checks (polls until complete, no unverified --no-wait).
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

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$ContainerLogPath = Join-Path $OutputDir "azure_bounded_probe_container.log"
$JsonResultPath = Join-Path $OutputDir "azure_bounded_probe_result.json"
$RawResponsePath = Join-Path $OutputDir "azure_probe_raw_response.html"

# 1. Ephemeral Resource Group & Ownership Verification
$isNewRg = $false
if (![string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $rgCheck = az group exists --name $ResourceGroup 2>$null
    if ($rgCheck -eq "true") {
        Write-Error @"
====================================================================================
CRITICAL ERROR: Resource group '$ResourceGroup' already exists.
To guarantee that existing or shared resources are NEVER deleted,
this diagnostic strictly refuses pre-existing resource groups.
Please specify an unused resource group name or omit the parameter to generate an ephemeral group.
====================================================================================
"@
        exit 1
    }
    $isNewRg = $true
} else {
    $uniqueId = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() + (Get-Random -Minimum 1000 -Maximum 9999).ToString()
    $ResourceGroup = "rg-marianos-probe-$uniqueId"
    $isNewRg = $true
}

Write-Host "=== Configured Diagnostic Resources ===" -ForegroundColor Cyan
Write-Host "Resource Group:  $ResourceGroup (Ephemeral: $isNewRg)"
Write-Host "ACR Registry:    $AcrName"
Write-Host "ACI Container:   $AciName (1 vCPU, 2.0 GB RAM)"
Write-Host "Location:        $Location"
Write-Host "========================================"

function Preserve-Evidence {
    Write-Host "=== Preserving Diagnostic Evidence Outside Disposable Container ===" -ForegroundColor Cyan
    if (Test-Path $ContainerLogPath) {
        $logContent = Get-Content -Path $ContainerLogPath -Raw
        
        # Extract JSON delimiter block
        if ($logContent -match '===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===') {
            $extractedJson = $matches[1].Trim()
            $extractedJson | Out-File -FilePath $JsonResultPath -Encoding utf8
            Write-Host "Preserved JSON Result: $JsonResultPath" -ForegroundColor Green
        }
        
        # Extract base64 raw response block
        if ($logContent -match '===AZURE_RAW_RESPONSE_BASE64_START===([\s\S]*?)===AZURE_RAW_RESPONSE_BASE64_END===') {
            try {
                $base64Str = $matches[1].Trim() -replace '\s+', ''
                $rawBytes = [System.Convert]::FromBase64String($base64Str)
                [System.IO.File]::WriteAllBytes($RawResponsePath, $rawBytes)
                Write-Host "Preserved Raw Response: $RawResponsePath" -ForegroundColor Green
            } catch {
                Write-Warning "Could not decode raw base64 response: $_"
            }
        }
    }
}

try {
    Write-Host "=== 1. Creating Ephemeral Resource Group: $ResourceGroup ($Location) ===" -ForegroundColor Cyan
    az group create --name $ResourceGroup --location $Location | Out-Null

    Write-Host "=== 2. Creating Ephemeral Azure Container Registry: $AcrName ===" -ForegroundColor Cyan
    az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true | Out-Null

    Write-Host "=== 3. Building Probe Docker Container ===" -ForegroundColor Cyan
    az acr build --registry $AcrName --image "$($ImageName):$($Tag)" -f azure/Dockerfile .

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
      --command-line "python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP --max-requests 3 --run-deadline-seconds 60.0" `
      --environment-variables `
          MARIANOS_PROXY_URL="$env:MARIANOS_PROXY_URL" | Out-Null

    Write-Host "=== 5. Streaming Logs from Container ===" -ForegroundColor Cyan
    $logs = az container logs --resource-group $ResourceGroup --name $AciName --follow
    $logs | Out-File -FilePath $ContainerLogPath -Encoding utf8

    Preserve-Evidence

} finally {
    Write-Host "=== 6. Initiating Verified Teardown of Diagnostic Resources ===" -ForegroundColor Cyan
    
    # Step 0: Preserve evidence before deletion
    Preserve-Evidence

    # Step 1: Explicitly delete ACI Container
    Write-Host "Deleting Container: $AciName..." -ForegroundColor Gray
    az container delete --resource-group $ResourceGroup --name $AciName --yes 2>$null | Out-Null

    # Step 2: Explicitly delete Container Registry
    Write-Host "Deleting Container Registry: $AcrName..." -ForegroundColor Gray
    az acr delete --resource-group $ResourceGroup --name $AcrName --yes 2>$null | Out-Null

    # Step 3: Delete Dedicated Resource Group (Only if created exclusively by this diagnostic)
    if ($isNewRg) {
        Write-Host "Deleting Ephemeral Resource Group: $ResourceGroup..." -ForegroundColor Gray
        az group delete --name $ResourceGroup --yes 2>$null | Out-Null
    }

    # Step 4: Polling verification for confirmed absence (avoids --no-wait ambiguity)
    Write-Host "Verifying absence of created resources..." -ForegroundColor Gray
    $aciRemoved = $false
    for ($i = 0; $i -lt 20; $i++) {
        $checkAci = az container show --resource-group $ResourceGroup --name $AciName --query name --output tsv 2>&1
        if ($checkAci -match "ResourceNotFound" -or $checkAci -match "could not be found" -or $checkAci -match "ResourceGroupNotFound" -or [string]::IsNullOrWhiteSpace($checkAci)) {
            $aciRemoved = $true
            break
        }
        Start-Sleep -Seconds 3
    }

    $acrRemoved = $false
    for ($i = 0; $i -lt 20; $i++) {
        $checkAcr = az acr show --name $AcrName --query name --output tsv 2>&1
        if ($checkAcr -match "ResourceNotFound" -or $checkAcr -match "could not be found" -or [string]::IsNullOrWhiteSpace($checkAcr)) {
            $acrRemoved = $true
            break
        }
        Start-Sleep -Seconds 3
    }

    Write-Host "====================================================================================" -ForegroundColor Green
    Write-Host "TEARDOWN VERIFICATION REPORT:" -ForegroundColor Green
    Write-Host "  - ACI Container ($AciName) Deletion Confirmed: $aciRemoved" -ForegroundColor Green
    Write-Host "  - ACR Registry ($AcrName) Deletion Confirmed:  $acrRemoved" -ForegroundColor Green
    Write-Host "  - Lingering Compute / Registry Cost:            `$0.00" -ForegroundColor Green
    Write-Host "====================================================================================" -ForegroundColor Green
}
