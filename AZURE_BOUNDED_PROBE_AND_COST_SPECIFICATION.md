# AZURE BOUNDED PROBE & DEPENDENCY COST SPECIFICATION (MARIANO'S ENTRY #36)

**Package:** Mariano's Scraper Entry #36  
**Authoritative Response to Review:** October 26 Comprehensive Review & Diagnostic Specification  
**Demonstration Store:** **Mariano's Vernon Hills (1720 N Milwaukee Ave, Vernon Hills, IL 60061, PICKUP)**  
**Baseline Store Separation:** 560-product baseline strictly maintained for New Eastside (Store `53100503`, `60601`)  
**Execution Authorization Status:** Standalone diagnostic plan submitted for review; **no unapproved cloud spending, instances, or proxy subscriptions active.**  
**Milestone Target:** **Wednesday, October 28, 2026** (Executable immediately at any time upon buyer authorization without reserving an appointment).

---

## 1. Dedicated Standalone Diagnostic Probe Specification

In direct response to reviewer requirements for an executable diagnostic with pinned versioning, strict circuit breakers, challenge classification, and verified cleanup:

### A. Manual-Only Execution Command
The bounded probe runs strictly as an isolated, manual diagnostic command. It does **not** create recurring triggers, Logic Apps, or scheduled jobs:
```powershell
# Local / Container Manual Probe Command
python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address "1720 N Milwaukee Ave, Vernon Hills, IL 60061" --zipcode 60061 --fulfillment-type PICKUP

# Dedicated Azure Container Deployment (Manual Single-Execution & Auto-Cleanup)
./azure/azure-deploy-bounded-probe.sh
# Or on Windows PowerShell:
./azure/azure-deploy-bounded-probe.ps1
```

### B. Enforced Circuit Breaker Limits & Guardrails

| Parameter | Enforced Limit | Implementation in `scripts/run_azure_bounded_probe.py` |
| :--- | :---: | :--- |
| **Pinned Version / Git Commit** | Pinned | Automatically records exact commit SHA-256 / HEAD hash into output artifact. |
| **Target Store & Address** | Vernon Hills | `1720 N Milwaukee Ave, Vernon Hills, IL 60061` (Store `#8502`, Division `531`, ID `53108502`). |
| **Fulfillment Context** | `PICKUP` | Verifies pickup fulfillment context in request and in-response metadata. |
| **Maximum Record Limit** | **Max 20 Items** | Hard ceiling via `--max-records-override 20` (stops parsing after 20 products). |
| **Maximum Page Depth** | **1 Page Only** | Probes single category page (`/d/meat-seafood`), zero deep pagination. |
| **Aggregate Request Count** | **Max 3 Requests** | Hard ceiling (max 5); execution immediately terminates if cap reached. |
| **Aggregate Retry Count** | **Max 1 Retry** | Single retry on network drop; stops immediately on failure. |
| **Whole-Run Deadline** | **60.0 Seconds** | Monotonic timer ceiling; aborts gracefully with `ABORTED_DEADLINE_EXCEEDED` if exceeded. |
| **Challenge Classifier** | Active Inspection | Classifies PerimeterX (`_pxAppId`, `px-captcha`, `challenge.js`, `Press & Hold`) and Akamai Bot Manager (`ak_bmsc`, `bm_sz`, Access Denied). |
| **Failure Stop Protocol** | Immediate Abort | If challenge/block detected or connection reset, stops immediately without hammering edge. |
| **Verified Cleanup** | Graceful Terminate | `finally` block terminates HTTP sessions, sockets, and browser processes with zero orphans. |
| **Durable Evidence Output** | JSON Artifact | Writes complete diagnostic metrics, headers, and store context to `logs/azure_bounded_probe_result.json`. |

---

## 2. Resource Sizing Alignment

All deployment scripts and specifications are strictly aligned to the lightweight container profile:

| Component | CPU Allocation | Memory Allocation | OS Runtime |
| :--- | :---: | :---: | :--- |
| **Bounded Diagnostic Probe** (`azure-deploy-bounded-probe.sh`) | **1 vCPU** | **2.0 GB RAM** | Linux Jammy / Python 3.11+ |
| **Production Scraper Stack** (`azure-deploy.sh` / `azure-deploy.ps1`) | **1 vCPU** | **2.0 GB RAM** | Linux Jammy / Python 3.11+ |
| **Container Engine** (`docker-compose.yml`) | **1 vCPU** | **2.0 GB RAM** | Playwright Stealth Headless |

---

## 3. Total One-Time Test Ceiling vs. Monthly Production Budget

To provide complete cost predictability, the one-time diagnostic test cost is strictly separated from the recurring monthly production estimate:

### A. Total One-Time Test Ceiling (Single Diagnostic Run)
*Calculated for 1 vCPU / 2.0 GB RAM running for ~2 minutes during the bounded probe:*

| Line Item | Execution Scope | Azure Retail Unit Pricing | Maximum Test Ceiling |
| :--- | :--- | :--- | :---: |
| **ACI Container Compute** | 1 vCPU, 2 GB for ~120 seconds | $0.0000135/vCPU-s + $0.0000015/GB-s | **$0.0020** |
| **Azure Container Registry (ACR)** | Basic Tier (1-day storage & build) | $0.167/day prorated + $0.0003/build-min | **$0.0200** |
| **Diagnostic Log Storage** | Hot LRS (1 PUT operation + ~5 KB JSON) | $0.018/GB-mo + $0.0004/10K ops | **$0.0010** |
| **Total Bandwidth Egress** | < 2.5 MB outbound data | First 100 GB/month egress is free | **$0.0000** |
| **TOTAL ONE-TIME TEST CEILING** | **Single Bounded Diagnostic Run** | **Complete Probe + Auto-Cleanup** | **< $0.05 (Five Cents)** |

### B. Monthly Production Estimate (Twice-Weekly Production Sweeps)
*Calculated separately for 8 full catalog sweeps per month across all 28 categories:*

| Component | Technical Specification | Execution Unit | Estimated Monthly Budget |
| :--- | :--- | :--- | :---: |
| **Azure Container Instances** | 1 vCPU, 2.0 GB Memory | ~15 minutes × 8 sweeps/month | **$0.18 – $0.35 / month** |
| **Azure Logic Apps** | Standard Consumption | 8 scheduled triggers/month | **< $0.01 / month** |
| **Azure Blob Storage** | Hot LRS (`marianos-scraped-data`) | ~1 MB JSON + 8 PUT ops/month | **< $0.01 / month** |
| **Optional Proxy Egress** | US Residential Proxy Pool (if Datacenter ASN blocked) | ~250 MB transfer per run | **$0.70 – $1.75 / month** (Optional) |
| **TOTAL RECURRING BUDGET** | **Full Production Deployment** | **Twice-Weekly Scheduled Runs** | **$0.20 – $2.10 / month** |

---

## 4. Reconciliation of Historical Simulation Logs

In accordance with reviewer instructions:
- `logs/azure_execution_history.log` has been reconciled and explicitly stamped with `[SIMULATION / OFFLINE ARCHITECTURAL HARNESS LOG]`.
- All October 18 and October 21 entries are formally designated as offline architectural harness simulations.
- **Affirmation:** As stated in all correspondence, zero live Azure runs have taken place. Live Azure execution remains strictly pending buyer review, approval, and environment provisioning.
- Baseline catalog data (`data/output/mariano_catalog_560.json`) remains strictly designated as 560 replay records for the New Eastside store (`53100503`), completely separate from the Vernon Hills (`1720 N Milwaukee Ave, 60061`) live diagnostic target.

---

## 5. Next Milestone Target

* **Proposed Delivery Target:** **Wednesday, October 28, 2026**
* **Readiness:** The dedicated diagnostic probe (`scripts/run_azure_bounded_probe.py`) and single-run deployment scripts (`azure/azure-deploy-bounded-probe.sh` / `.ps1`) are packaged, tested, and ready for immediate manual execution at any time once approved.
