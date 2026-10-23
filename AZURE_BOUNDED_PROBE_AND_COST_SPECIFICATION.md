# AZURE BOUNDED PROBE & DEPENDENCY COST SPECIFICATION

**Package:** Mariano's Scraper Entry #36 (and Walmart Scraper Entry #20)  
**Authoritative Response to Review Target:** October 22 Evening Review — Item 3 & Bounded Probe Requirement  
**Next Inspectable Delivery Target:** **Proposed: October 26, 2026 (Subject to Buyer Authorization)**  

---

## 1. Precise Bounded Probe Specification

In accordance with reviewer instructions ("*An Azure-ready configuration is not proof Azure resolves the timeout. Report the precise bounded probe and dependency/cost requirements separately; no new access or services are approved here*"):

| Parameter | Bound / Limit | Description |
| :--- | :--- | :--- |
| **Execution Environment** | Azure Container Instances (ACI) | US East (Virginia) or US North Central (Chicago, IL) |
| **Target Store Context** | Store ID `53100503` | Mariano's New Eastside, 333 E Benton Pl, Chicago, IL 60601 |
| **Target Probe Route** | 1 Route Only | Category 05: `Dairy & Eggs::Milk & Plant Alternatives` |
| **Maximum Page Depth** | 1 Page (`page=1`) | No deep pagination during probe |
| **Maximum Record Limit** | 10 to 20 Products | Strict hard ceiling (`max_records_override=20`) |
| **Timeout Ceiling** | 15.0 seconds per request | Fast fail-safe to prevent hanging |
| **Total Probe Egress** | < 2.5 MB | Negligible bandwidth footprint |
| **Output Artifact** | `logs/azure_bounded_probe_result.json` | Stores HTTP status, Akamai headers, store context, and latency |

### Probe Objective:
Establish conclusive machine-readable proof that outbound traffic from a US-based Azure node receives HTTP 200 OK from `www.marianos.com` (resolving the TCP reset/timeout observed on non-US IP `103.106.236.167`) before executing full production sweeps.

---

## 2. Cloud Dependency & Cost Requirements

All components are strictly scoped to minimal open-standard infrastructure. **No unapproved access, paid services, or multi-node clusters are provisioned.**

| Component | Technical Specification | Execution Unit | Unit Price | Estimated Monthly Cost (8 Runs/Mo) |
| :--- | :--- | :--- | :--- | :--- |
| **Azure Container Instances** | 1 vCPU, 2.0 GB Memory, Linux Jammy | ~15 minutes per production run | $0.0000135/vCPU-s + $0.0000015/GB-s | **$0.18 – $0.35 / month** |
| **Azure Logic Apps** | Standard Consumption (Recurrence Trigger) | 8 triggers per month (Sun & Wed 04:00 UTC) | $0.000025 per execution | **< $0.01 / month** |
| **Azure Blob Storage** | Hot LRS (Container: `marianos-scraped-data`) | ~1 MB JSON storage + 8 PUT ops | $0.018 per GB/month | **< $0.01 / month** |
| **Optional Proxy Egress** | US Residential Proxy Pool (if Datacenter ASN blocked) | ~250 MB data transfer per run | $3.50 per GB bandwidth | **$0.70 – $1.75 / month** (Optional) |
| **TOTAL ESTIMATED BUDGET** | **Pre-Configured Architecture** | **Twice-Weekly Production Sweep** | — | **$0.20 – $2.10 / month** |

> [!IMPORTANT]
> **Strict Governance Statement:**  
> In compliance with review stipulations, **zero paid cloud services or recurring instances will be created without explicit buyer authorization.** The deployment script (`azure/azure-deploy.sh` / `azure/azure-deploy.ps1`) is completely self-contained and ready to be deployed directly within the buyer's own Azure subscription at their discretion.

---

## 3. Next Inspectable Delivery Date

* **Proposed Delivery Target:** **Monday, October 26, 2026 (Subject to Buyer Access Approval)**
* **Target Deliverables for October 26:**
  1. Resulting evidence log from the bounded probe (`logs/azure_bounded_probe_result.json`).
  2. Assortment retention verification report demonstrating indefinite preservation of out-of-stock items and carried-forward vs. fresh observation timestamps.
  3. Reconciled category coverage report for all 14 parent CSV brief URLs and 28 subcategories.
