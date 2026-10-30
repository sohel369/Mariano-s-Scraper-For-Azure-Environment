# AZURE BOUNDED PROBE & DEPENDENCY COST SPECIFICATION (MARIANO'S ENTRY #36)

**Package:** Mariano's Scraper Entry #36  
**Authoritative Response to Review:** October 30 Review & Strict Diagnostic Guardrails  
**Target Demonstration Store:** **Mariano's Vernon Hills (1720 N Milwaukee Ave, Vernon Hills, IL 60061, PICKUP)**  
- **Official Retailer URL:** `https://www.marianos.com/stores/grocery/il/vernon-hills/marianos-vernon-hills/531/00502`  
- **Retailer IDs:** Division `531`, Store Number `00502`, Store ID `53100502` (exact matching; conflicting IDs like `99900502` strictly rejected)  
**Baseline Store Separation:** 560-product baseline strictly designated as **Unverified Replay Baseline** for historical New Eastside (Store `53100503`, `60601`). No live provenance is claimed for the baseline.  
**Execution Authorization Status:** Standalone diagnostic plan submitted for review; **no unapproved cloud spending, instances, or proxy subscriptions active.**  
**Milestone Target:** **Saturday, October 31, 2026 at 18:00 UTC (14:00 EDT / 13:00 CDT)** (Executable immediately at any time upon buyer authorization without reserving an appointment).

---

## 1. Dedicated Standalone Diagnostic Probe Specification

In direct response to reviewer requirements for an executable diagnostic with pinned versioning, strict circuit breakers, pre-dispatch attempt counting, challenge classification, genuine parsing (zero mock records), and verified cleanup:

### A. Manual-Only Execution Command
The bounded probe runs strictly as an isolated, manual diagnostic command. It does **not** create recurring triggers, Logic Apps, or scheduled jobs:
```powershell
# Standalone Manual Probe Execution:
python scripts/run_azure_bounded_probe.py --max-records-override 20 --store-address "1720 N Milwaukee Ave, Vernon Hills, IL 60061" --zipcode 60061 --fulfillment-type PICKUP --max-requests 3 --max-retries 1 --run-deadline-seconds 60.0

# Dedicated Azure Container Deployment (Manual Single-Execution, External Evidence Extraction & Guaranteed Teardown)
./azure/azure-deploy-bounded-probe.sh
# Or on Windows PowerShell:
./azure/azure-deploy-bounded-probe.ps1
```

### B. Enforced Circuit Breaker Limits & Failure Guardrails

| Parameter | Enforced Limit | Implementation in `scripts/run_azure_bounded_probe.py` |
| :--- | :---: | :--- |
| **Pinned Version / Git Commit** | Pinned | Automatically records exact commit SHA-256 / HEAD hash into output artifact. |
| **Target Store & Address** | Vernon Hills | `1720 N Milwaukee Ave, Vernon Hills, IL 60061` (Store `#00502`, Division `531`, ID `53100502`). Conflicting IDs (e.g. `99900502`) strictly rejected. |
| **Fulfillment Modality** | `PICKUP` | Establishes `kroger.modality=PICKUP` and `kroger.storeId=53100502` session cookies. Requires explicit `PICKUP` modality in payload; absent modality fails. |
| **Structural Store Validation** | Exact & Price-Bound | Structural verification of division 531, store 00502, and explicit pickup modality with price-bearing source context; cookie-only or unrelated text matches strictly fail. |
| **Genuine Parsing Only** | Zero Mock Data | **Zero generated/synthetic records.** Uses `MarianoPageParser` to parse actual HTML/JSON, or reports 0 products truthfully. |
| **Non-Success HTTP Stops** | Immediate Abort | HTTP != 200 (e.g. 500, 403, 404) immediately sets failing status and exits with status code 1. |
| **Maximum Record Limit** | **Max 20 Items** | Hard ceiling via `--max-records-override 20` (stops parsing after 20 products; all 20 rows preserved in output). |
| **Maximum Page Depth** | **1 Page Only** | Probes single category page (`/d/meat-seafood`), zero deep pagination. |
| **Pre-Dispatch Attempt Counter** | **Max 3 Requests** | Counts attempts **before** dispatch via `BoundedRequestAdapter`; counts timeouts and redirect hops against ceiling. |
| **Aggregate Retry Limit** | **Max 1 Retry** | Single retry on network drop; stops immediately on failure. |
| **Whole-Run Deadline** | **60.0 Seconds** | Monotonic timer ceiling covering connection, redirects, body reading, parsing, and export. Aborts with exit code 1 if exceeded. |
| **Response Byte Ceiling** | **2.5 MB Max** | Streams response in chunks; aborts with `ABORTED_BYTE_LIMIT_EXCEEDED` if body exceeds 2.5 MB. |
| **Challenge Classifier** | Active Inspection | Classifies PerimeterX (`_pxAppId`, `px-captcha`, `challenge.js`, `Press & Hold`) and Akamai Bot Manager (`ak_bmsc`, `bm_sz`, Access Denied). |
| **Durable Evidence Extraction** | Externalized | Result JSON and raw response HTML extracted outside the container prior to container deletion. |
| **Resource Group Protection** | Dedicated / Refused | Strictly refuses pre-existing resource groups to prevent deleting shared resources; auto-generates dedicated ephemeral group. |
| **Guaranteed Resource Teardown** | Active Polling | Deletes ACI container AND deletes ephemeral ACR registry; active polling confirms absence without unverified `--no-wait`. |

---

## 2. Resource Sizing Alignment

All deployment scripts and specifications are strictly aligned to the lightweight container profile:

| Component | CPU Allocation | Memory Allocation | OS Runtime |
| :--- | :---: | :---: | :--- |
| **Bounded Diagnostic Probe** (`azure-deploy-bounded-probe.sh` / `.ps1`) | **1 vCPU** | **2.0 GB RAM** | Linux Jammy / Python 3.11+ |
| **Production Scraper Stack** (`azure-deploy.sh` / `azure-deploy.ps1`) | **1 vCPU** | **2.0 GB RAM** | Linux Jammy / Python 3.11+ |
| **Container Engine** (`docker-compose.yml`) | **1 vCPU** | **2.0 GB RAM** | Playwright Stealth Headless |

---

## 3. Total One-Time Test Ceiling vs. Monthly Production Budget

To provide complete cost predictability and eliminate cost table contradictions, the one-time diagnostic test cost is strictly separated from the recurring monthly production estimate:

### A. Total One-Time Test Ceiling (Single Diagnostic Run)
*Calculated for 1 vCPU / 2.0 GB RAM running for ~2 minutes during the bounded probe, with immediate ACR teardown:*

| Line Item | Execution Scope | Azure Retail Unit Pricing | Maximum Test Ceiling |
| :--- | :--- | :--- | :---: |
| **ACI Container Compute** | 1 vCPU, 2 GB for ~120 seconds | $0.0000135/vCPU-s + $0.0000015/GB-s | **$0.0020** |
| **Azure Container Registry (ACR)** | Basic Tier (Prorated ~15 min ephemeral lifecycle) | $0.167/day ($0.007/hour); auto-deleted by script | **$0.0050** |
| **ACR 24-Hour Safety Margin** | (In the event ACR is left for full 24 hours before deletion) | Standard Azure Basic ACR daily rate | *$0.1670 max* |
| **Diagnostic Log Storage** | Hot LRS (1 PUT operation + ~5 KB JSON) | $0.018/GB-mo + $0.0004/10K ops | **$0.0010** |
| **Total Bandwidth Egress** | < 2.5 MB outbound data | First 100 GB/month egress is free | **$0.0000** |
| **TOTAL ONE-TIME TEST CEILING** | **Immediate Teardown (Normal Path)** | **Complete Probe + Auto-Cleanup** | **< $0.01 (One Cent)** |
| **TOTAL ONE-TIME TEST CEILING** | **24-Hour ACR Retention Margin** | **Absolute worst-case uncleaned ACR** | **< $0.20 (Twenty Cents)** |

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

## 4. Reconciliation of Historical Simulation Logs & Baseline Designation

In accordance with reviewer instructions:
- `logs/azure_execution_history.log` and `logs/azure_scheduled_run_evidence.json` have been reconciled and explicitly stamped as offline simulation harness logs (`[SIMULATION / OFFLINE HARNESS TEST - ZERO LIVE AZURE RUNS OCCURRED]`).
- All October 18 and October 21 entries are formally designated as offline architectural harness simulations.
- **Formally Designated Unverified Replay Baseline:** The 560 baseline catalog records (`data/output/mariano_catalog_560.json`) match fixture tuples and check digits, establishing schema and offline test overlap, but remain designated as **Unverified Replay Baseline** pending genuine live collection evidence.
- The demonstration store target is strictly **Mariano's Vernon Hills (1720 N Milwaukee Ave, Store #00502, Division 531, ID 53100502)**, completely separate from the New Eastside replay baseline.

---

## 5. Next Milestone Target

* **Proposed Delivery Target:** **Thursday, October 29, 2026 at 18:00 UTC (14:00 EDT)**
* **Readiness:** The dedicated diagnostic probe (`scripts/run_azure_bounded_probe.py`) and single-run deployment scripts (`azure/azure-deploy-bounded-probe.sh` / `.ps1`) are packaged, tested, and ready for immediate manual execution at any time once approved.
