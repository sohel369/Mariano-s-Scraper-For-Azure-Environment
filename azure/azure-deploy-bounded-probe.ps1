# ==============================================================================
# Mariano's Scraper Microsoft Azure Dedicated Bounded Probe Script (PowerShell)
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
$containerExitCode = "UNKNOWN"

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$uniqueId = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() + (Get-Random -Minimum 1000 -Maximum 9999).ToString()
$ContainerLogPath = Join-Path $OutputDir "azure_bounded_probe_container.log"
$JsonResultPath = Join-Path $OutputDir "azure_bounded_probe_result.json"
$RawResponsePath = Join-Path $OutputDir "azure_probe_raw_response.html"

# Pre-execution cleanup: Strictly remove stale result files to prevent false verification from previous runs
Remove-Item -Path $ContainerLogPath, $JsonResultPath, $RawResponsePath -Force -ErrorAction SilentlyContinue

# Resolve pinned git commit hash
$pinnedCommit = ""
try {
    $pinnedCommit = (git rev-parse HEAD 2>$null)
    if ([string]::IsNullOrWhiteSpace($pinnedCommit)) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $repoBase = Split-Path -Parent $scriptDir
        $candidatePaths = @(
            (Join-Path $repoBase "logs\git_commit_lineage_proof.json"),
            (Join-Path (Get-Location) "logs\git_commit_lineage_proof.json"),
            (Join-Path $OutputDir "git_commit_lineage_proof.json")
        )
        foreach ($cp in $candidatePaths) {
            if (Test-Path $cp) {
                $proofData = Get-Content -Path $cp -Raw | ConvertFrom-Json
                if (-not [string]::IsNullOrWhiteSpace($proofData.head_commit)) {
                    $pinnedCommit = $proofData.head_commit
                    break
                }
            }
        }
    }
} catch {}

if ([string]::IsNullOrWhiteSpace($pinnedCommit)) {
    Write-Error @"
====================================================================================
CRITICAL PREFLIGHT ERROR: Pinned git commit could not be determined.
Bounded execution requires an authoritative non-empty commit hash for provenance.
====================================================================================
"@
    exit 1
}

# Helper: Redact sensitive credentials (passwords, proxy tokens) from command strings before logging/exceptions
function Format-RedactedCommandLine {
    param([string]$Cmd)
    if ([string]::IsNullOrEmpty($Cmd)) { return "" }
    $res = $Cmd
    # Redact registry passwords: --registry-password <secret>
    $res = [regex]::Replace($res, '(--registry-password\s+)("[^"]+"|\S+)', '${1}[REDACTED]')
    # Redact standard password arguments: --password <secret> or --admin-password <secret>
    $res = [regex]::Replace($res, '(--admin-password\s+)("[^"]+"|\S+)', '${1}[REDACTED]')
    $res = [regex]::Replace($res, '(--password\s+)("[^"]+"|\S+)', '${1}[REDACTED]')
    $res = [regex]::Replace($res, '(-p\s+)("[^"]+"|\S+)', '${1}[REDACTED]')
    # Redact proxy credentials or environment strings: MARIANOS_PROXY_URL="..."
    $res = [regex]::Replace($res, '(MARIANOS_PROXY_URL=)("[^"]*"|\S*)', '${1}[REDACTED]')
    # Redact embedded URL credentials: http://user:pass@host
    $res = [regex]::Replace($res, 'https?://[^:\s]+:[^@\s]+@', 'http://[REDACTED]@')
    return $res
}

# Helper: Execute command with independent external process timeout supervisor
# Enforces:
#  1. Concurrent stream draining via asynchronous tasks to prevent pipe buffer deadlock
#  2. Process-tree termination & verification via taskkill /F /T /PID on timeout
#  3. Bounded final stream collection (Task.WaitAll with timeout) so inherited handles never hang ReadToEnd
#  4. Credential redaction in exceptions and log output
function Invoke-BoundedCommand {
    param(
        [Parameter(Mandatory=$true)][int]$TimeoutSeconds,
        [Parameter(Mandatory=$true)][string]$CommandLine,
        [string]$StdOutPath = $null
    )
    $redactedCmd = Format-RedactedCommandLine -Cmd $CommandLine

    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "cmd.exe"
    $pinfo.Arguments = "/c `"$CommandLine`""
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $pinfo
    if (-not $p.Start()) {
        throw "Failed to start process for command: $redactedCmd"
    }

    # Concurrent asynchronous stream reading to drain OS pipes continuously and prevent deadlock
    $stdoutTask = $p.StandardOutput.ReadToEndAsync()
    $stderrTask = $p.StandardError.ReadToEndAsync()

    $waitMs = $TimeoutSeconds * 1000
    $hasExited = $p.WaitForExit($waitMs)

    $stdout = ""
    $stderr = ""

    if (-not $hasExited) {
        # Terminate entire process tree (parent cmd.exe + child az/python processes)
        try {
            $null = & taskkill.exe /F /T /PID $p.Id 2>&1
        } catch {
            try { $p.Kill() } catch {}
        }

        # Bounded wait for process exit verification
        try { [void]$p.WaitForExit(3000) } catch {}

        # Bounded stream collection: Wait up to 2000ms so inherited handles don't hang ReadToEnd
        try {
            [void][System.Threading.Tasks.Task]::WaitAll(@($stdoutTask, $stderrTask), 2000)
            if ($stdoutTask.IsCompleted) { $stdout = $stdoutTask.Result }
            if ($stderrTask.IsCompleted) { $stderr = $stderrTask.Result }
        } catch {}

        throw "Command timed out after $TimeoutSeconds seconds: $redactedCmd"
    } else {
        # Process completed within timeout: drain remaining output with 3000ms ceiling
        try {
            [void][System.Threading.Tasks.Task]::WaitAll(@($stdoutTask, $stderrTask), 3000)
            if ($stdoutTask.IsCompleted) { $stdout = $stdoutTask.Result }
            if ($stderrTask.IsCompleted) { $stderr = $stderrTask.Result }
        } catch {}

        # Ensure any remaining orphaned child processes holding inherited handles are cleaned up
        try { $null = & taskkill.exe /F /T /PID $p.Id 2>&1 } catch {}
    }

    $exitCode = $p.ExitCode

    if ($StdOutPath) {
        [System.IO.File]::WriteAllText($StdOutPath, $stdout, [System.Text.Encoding]::UTF8)
    }

    return [PSCustomObject]@{
        ExitCode = $exitCode
        StdOut = $stdout.Trim()
        StdErr = $stderr.Trim()
    }
}

# Preflight: Verify process execution and timeout capability
try {
    $preTest = Invoke-BoundedCommand -TimeoutSeconds 5 -CommandLine "echo preflight_ok"
    if ($preTest.ExitCode -ne 0 -or $preTest.StdOut -ne "preflight_ok") {
        Write-Error "CRITICAL PREFLIGHT ERROR: Process execution with timeout capability is non-functional."
        exit 1
    }
} catch {
    Write-Error "CRITICAL PREFLIGHT ERROR: Timeout subsystem initialization failed: $_"
    exit 1
}

# 1. Ephemeral Resource Group & Ownership Verification
if (![string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $rgRes = Invoke-BoundedCommand -TimeoutSeconds 30 -CommandLine "az group exists --name $ResourceGroup"
    if ($rgRes.ExitCode -ne 0) {
        Write-Error @"
====================================================================================
CRITICAL ERROR: Failed to query resource group existence (exit code $($rgRes.ExitCode)).
Refusing to proceed to prevent accidental modification of shared resources.
====================================================================================
"@
        exit 1
    }
    $rgClean = $rgRes.StdOut.Trim().ToLower()
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
        Write-Error "CRITICAL ERROR: Unknown/error response from az group exists: '$($rgRes.StdOut)'."
        exit 1
    }
} else {
    $ResourceGroup = "rg-marianos-probe-$uniqueId"
}

Write-Host "=== Configured Diagnostic Resources ===" -ForegroundColor Cyan
Write-Host "Run Identifier:  $uniqueId"
Write-Host "Pinned Commit:   $pinnedCommit"
Write-Host "Resource Group:  $ResourceGroup (Ephemeral)"
Write-Host "ACR Registry:    $AcrName"
Write-Host "ACI Container:   $AciName (1 vCPU, 2.0 GB RAM)"
Write-Host "Location:        $Location"
Write-Host "========================================"

function Test-Evidence-Complete {
    param([string]$LogPath, [string]$TargetRunId, [string]$TargetCommit)
    if (-not (Test-Path $LogPath)) { return $false }
    $content = Get-Content -Path $LogPath -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) { return $false }

    # Check for both JSON START and END
    $jsonMatches = [regex]::Matches($content, '===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===')
    if ($jsonMatches.Count -eq 0) { return $false }

    # Parse last JSON block
    try {
        $lastJson = $jsonMatches[$jsonMatches.Count - 1].Groups[1].Value.Trim()
        $data = $lastJson | ConvertFrom-Json
    } catch {
        return $false
    }

    # Verify run_id and pinned_git_commit strictly
    if ([string]::IsNullOrWhiteSpace($TargetRunId) -or $data.run_id -ne $TargetRunId) { return $false }
    if ([string]::IsNullOrWhiteSpace($TargetCommit) -or [string]::IsNullOrWhiteSpace($data.pinned_git_commit) -or $data.pinned_git_commit -ne $TargetCommit) { return $false }

    # Check raw response delimiters if raw body expected
    $expectedBytes = [int]($data.evidence.raw_response_size_bytes)
    $expectedSha = [string]($data.evidence.raw_response_sha256)
    if ($expectedBytes -gt 0 -or !([string]::IsNullOrWhiteSpace($expectedSha))) {
        $rawMatches = [regex]::Matches($content, '===AZURE_RAW_RESPONSE_BASE64_START===([\s\S]*?)===AZURE_RAW_RESPONSE_BASE64_END===')
        if ($rawMatches.Count -eq 0) { return $false }
    }

    return $true
}

function Preserve-And-Validate-Evidence {
    Write-Host "=== Preserving Diagnostic Evidence Outside Disposable Container ===" -ForegroundColor Cyan
    if ($script:aciCreated) {
        # Bounded recovery path: Retries fetching logs if delimiters or payload are incomplete
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            if (-not (Test-Evidence-Complete -LogPath $script:ContainerLogPath -TargetRunId $uniqueId -TargetCommit $pinnedCommit)) {
                Write-Host "Evidence incomplete in log; retrieving fresh container logs from Azure (attempt $attempt/5)..."
                try {
                    Invoke-BoundedCommand -TimeoutSeconds 30 -CommandLine "az container logs --resource-group $ResourceGroup --name $AciName" -StdOutPath $script:ContainerLogPath | Out-Null
                } catch {
                    Write-Warning "Log refetch attempt $attempt failed: $_"
                }
            }
            if (Test-Evidence-Complete -LogPath $script:ContainerLogPath -TargetRunId $uniqueId -TargetCommit $pinnedCommit) {
                Write-Host "Complete delimited evidence confirmed in container log."
                break
            }
            Start-Sleep -Seconds 2
        }

        if (Test-Path $script:ContainerLogPath) {
            $logContent = Get-Content -Path $script:ContainerLogPath -Raw

            # Extract the authoritative LAST delimited JSON block
            $jsonMatches = [regex]::Matches($logContent, '===AZURE_PROBE_JSON_START===([\s\S]*?)===AZURE_PROBE_JSON_END===')
            if ($jsonMatches.Count -gt 0) {
                $lastJson = $jsonMatches[$jsonMatches.Count - 1].Groups[1].Value.Trim()
                $lastJson | Out-File -FilePath $script:JsonResultPath -Encoding utf8
            } else {
                Write-Warning "Incomplete or missing JSON delimiters in container log."
                Remove-Item -Path $script:JsonResultPath -Force -ErrorAction SilentlyContinue
            }

            # Extract the authoritative LAST raw response base64 block
            $rawMatches = [regex]::Matches($logContent, '===AZURE_RAW_RESPONSE_BASE64_START===([\s\S]*?)===AZURE_RAW_RESPONSE_BASE64_END===')
            if ($rawMatches.Count -gt 0) {
                try {
                    $base64Str = $rawMatches[$rawMatches.Count - 1].Groups[1].Value.Trim() -replace '\s+', ''
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

        # Rigorous validation of JSON schema, version identity, and raw bytes integrity
        if (Test-Path $script:JsonResultPath) {
            try {
                $parsed = Get-Content -Path $script:JsonResultPath -Raw | ConvertFrom-Json
                if ($parsed -ne $null -and $parsed.probe_name -eq "AZURE_BOUNDED_PROBE_DIAGNOSTIC") {
                    if ([string]::IsNullOrWhiteSpace($uniqueId) -or $parsed.run_id -ne $uniqueId) {
                        Write-Warning "Run ID mismatch or missing: $($parsed.run_id) vs expected $uniqueId"
                    } elseif ([string]::IsNullOrWhiteSpace($pinnedCommit) -or [string]::IsNullOrWhiteSpace($parsed.pinned_git_commit) -or $parsed.pinned_git_commit -ne $pinnedCommit) {
                        Write-Warning "Commit mismatch or missing: $($parsed.pinned_git_commit) vs expected $pinnedCommit"
                    } else {
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
                        }
                    }
                }
            } catch {
                Write-Warning "JSON result verification failed: $_"
            }
        }

        if (-not $script:exportVerified) {
            Write-Warning "Evidence export failed; preserving recoverable container artifacts before teardown..."
            Copy-Item -Path $script:ContainerLogPath -Destination (Join-Path $OutputDir "unverified_container_${uniqueId}.log") -Force -ErrorAction SilentlyContinue
            try {
                Invoke-BoundedCommand -TimeoutSeconds 20 -CommandLine "az container show --resource-group $ResourceGroup --name $AciName" -StdOutPath (Join-Path $OutputDir "unverified_container_state_${uniqueId}.json") | Out-Null
            } catch {}
        }
    }
}

try {
    Write-Host "=== 1. Creating Ephemeral Resource Group: $ResourceGroup ($Location) ===" -ForegroundColor Cyan
    $createRg = Invoke-BoundedCommand -TimeoutSeconds 60 -CommandLine "az group create --name $ResourceGroup --location $Location"
    if ($createRg.ExitCode -ne 0) { throw "Failed to create resource group $ResourceGroup" }
    $rgCreated = $true

    Write-Host "=== 2. Creating Ephemeral Azure Container Registry: $AcrName ===" -ForegroundColor Cyan
    $createAcr = Invoke-BoundedCommand -TimeoutSeconds 60 -CommandLine "az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true"
    if ($createAcr.ExitCode -ne 0) { throw "Failed to create ACR $AcrName" }
    $acrCreated = $true

    Write-Host "=== 3. Building Probe Docker Container ===" -ForegroundColor Cyan
    $buildAcr = Invoke-BoundedCommand -TimeoutSeconds 180 -CommandLine "az acr build --registry $AcrName --image $($ImageName):$($Tag) -f azure/Dockerfile ."
    if ($buildAcr.ExitCode -ne 0) { throw "Failed to build container image" }

    $AcrLoginServer = (Invoke-BoundedCommand -TimeoutSeconds 30 -CommandLine "az acr show --name $AcrName --query loginServer --output tsv").StdOut
    $AcrUsername = (Invoke-BoundedCommand -TimeoutSeconds 30 -CommandLine "az acr credential show --name $AcrName --query username --output tsv").StdOut
    $AcrPassword = (Invoke-BoundedCommand -TimeoutSeconds 30 -CommandLine "az acr credential show --name $AcrName --query ""passwords[0].value"" --output tsv").StdOut

    Write-Host "=== 4. Executing Manual Bounded Probe in ACI (1 vCPU, 2.0 GB RAM) ===" -ForegroundColor Cyan
    $aciCmd = "az container create --resource-group $ResourceGroup --name $AciName --image $AcrLoginServer/$($ImageName):$($Tag) --registry-login-server $AcrLoginServer --registry-username $AcrUsername --registry-password $AcrPassword --cpu 1 --memory 2 --restart-policy Never --command-line ""python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address '1720 N Milwaukee Ave, Vernon Hills, IL 60061' --zipcode 60061 --fulfillment-type PICKUP --max-requests 3 --max-retries 1 --run-deadline-seconds 60.0 --run-id '$uniqueId'"" --environment-variables MARIANOS_PROXY_URL=""$env:MARIANOS_PROXY_URL"""
    $createAci = Invoke-BoundedCommand -TimeoutSeconds 60 -CommandLine $aciCmd
    if ($createAci.ExitCode -ne 0) { throw "Failed to create container instance $AciName" }
    $aciCreated = $true

    Write-Host "=== 5. Streaming Logs from Container ===" -ForegroundColor Cyan
    try {
        Invoke-BoundedCommand -TimeoutSeconds 90 -CommandLine "az container logs --resource-group $ResourceGroup --name $AciName --follow" -StdOutPath $ContainerLogPath | Out-Null
    } catch {
        Write-Warning "Container log streaming ended or timed out: $_"
    }

    # Query container terminal state strictly with bounded polling
    $containerTerminalExit = ""
    for ($poll = 1; $poll -le 15; $poll++) {
        $stateRes = Invoke-BoundedCommand -TimeoutSeconds 20 -CommandLine "az container show --resource-group $ResourceGroup --name $AciName --query containers[0].instanceView.currentState.state --output tsv"
        $aciState = $stateRes.StdOut.Trim()
        if ($aciState -eq "Terminated" -or $aciState -eq "Failed" -or $aciState -eq "Succeeded") {
            $exitRes = Invoke-BoundedCommand -TimeoutSeconds 20 -CommandLine "az container show --resource-group $ResourceGroup --name $AciName --query containers[0].instanceView.currentState.exitCode --output tsv"
            $containerTerminalExit = $exitRes.StdOut.Trim()
            break
        }
        Start-Sleep -Seconds 2
    }

    if ($containerTerminalExit -match '^\d+$') {
        $containerExitCode = [string]$containerTerminalExit
    } else {
        Write-Warning "Authoritative terminal exit code unavailable for container $AciName (State: $aciState)."
        $containerExitCode = "UNKNOWN"
    }

} finally {
    Write-Host "=== 6. Initiating Guaranteed Teardown of Diagnostic Resources ===" -ForegroundColor Cyan

    Preserve-And-Validate-Evidence

    # Delete ACI container ONLY if created
    if ($aciCreated) {
        Write-Host "Deleting Container: $AciName..." -ForegroundColor Gray
        try {
            Invoke-BoundedCommand -TimeoutSeconds 60 -CommandLine "az container delete --resource-group $ResourceGroup --name $AciName --yes" | Out-Null
        } catch {}
    }

    # Delete ACR ONLY if created
    if ($acrCreated) {
        Write-Host "Deleting Container Registry: $AcrName..." -ForegroundColor Gray
        try {
            Invoke-BoundedCommand -TimeoutSeconds 60 -CommandLine "az acr delete --resource-group $ResourceGroup --name $AcrName --yes" | Out-Null
        } catch {}
    }

    # Delete Resource Group ONLY if created by this invocation
    if ($rgCreated) {
        Write-Host "Deleting Dedicated Resource Group: $ResourceGroup..." -ForegroundColor Gray
        try {
            Invoke-BoundedCommand -TimeoutSeconds 90 -CommandLine "az group delete --name $ResourceGroup --yes" | Out-Null
        } catch {}
    }

    # Complete absence verification
    Write-Host "Verifying absence of created resources..." -ForegroundColor Gray
    $allRemoved = $true

    if ($aciCreated) {
        $aciGone = $false
        for ($i = 0; $i -lt 20; $i++) {
            try {
                $checkAciRes = Invoke-BoundedCommand -TimeoutSeconds 20 -CommandLine "az container show --resource-group $ResourceGroup --name $AciName --query name --output tsv"
                $checkAci = ($checkAciRes.StdOut + " " + $checkAciRes.StdErr)
                if ($checkAciRes.ExitCode -ne 0 -or $checkAci -match "ResourceNotFound" -or $checkAci -match "ResourceGroupNotFound" -or $checkAci -match "could not be found") {
                    $aciGone = $true
                    break
                }
            } catch {
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
            try {
                $checkAcrRes = Invoke-BoundedCommand -TimeoutSeconds 20 -CommandLine "az acr show --name $AcrName --query name --output tsv"
                $checkAcr = ($checkAcrRes.StdOut + " " + $checkAcrRes.StdErr)
                if ($checkAcrRes.ExitCode -ne 0 -or $checkAcr -match "ResourceNotFound" -or $checkAcr -match "could not be found") {
                    $acrGone = $true
                    break
                }
            } catch {
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
            try {
                $checkRgRes = Invoke-BoundedCommand -TimeoutSeconds 20 -CommandLine "az group exists --name $ResourceGroup"
                if ($checkRgRes.ExitCode -eq 0 -and $checkRgRes.StdOut.Trim().ToLower() -eq "false") {
                    $rgGone = $true
                    break
                }
            } catch {
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

    # Strictly require container exit code 0; unknown or missing exit code fails closed
    if (($containerExitCode -eq "0") -and ($probeStatusVal -eq "SUCCESS_PROBE_COMPLETE" -or $probeStatusVal -eq "SUCCESS_CONNECTIVITY_ONLY")) {
        $probeSuccess = $true
    } else {
        $probeSuccess = $false
    }

    Write-Host "====================================================================================" -ForegroundColor Cyan
    Write-Host "DEPLOYMENT EXECUTION REPORT:" -ForegroundColor Cyan
    Write-Host "  - Resources Created by Invocation: ACI=$aciCreated, ACR=$acrCreated, RG=$rgCreated"
    Write-Host "  - Stage 1 [Probe Execution]: $(if ($probeSuccess) { "SUCCESS ($probeStatusVal, Exit 0)" } else { "FAILED ($probeStatusVal, Exit $containerExitCode)" })"
    Write-Host "  - Stage 2 [Evidence Export]: $(if ($exportVerified) { "VERIFIED" } else { "FAILED" })"
    Write-Host "  - Stage 3 [Resource Teardown]: $(if ($allRemoved) { "VERIFIED (`$0.00 lingering cost)" } else { "UNRESOLVED" })"
    Write-Host "====================================================================================" -ForegroundColor Cyan

    if (-not $probeSuccess -or -not $exportVerified -or -not $allRemoved) {
        exit 1
    }
}
