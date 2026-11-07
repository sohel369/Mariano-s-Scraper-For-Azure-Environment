# GIT PROVENANCE & FILE INTEGRITY MANIFEST

**Generated UTC:** 2026-11-07T18:38:54.118007+00:00  
**Repository URL:** [https://github.com/sohel369/Mariano-s-Scraper-For-Azure-Environment.git](https://github.com/sohel369/Mariano-s-Scraper-For-Azure-Environment.git)  
**Branch:** `main`  
**HEAD Commit:** `5ea61b8dbd5626cf0c9c17c6dbe71d2febf1c855`  
**Working Tree Clean:** `True`  

## 1. Recent Authoritative Commits
```text
5ea61b8 Update provenance manifest and checksums for implementation commit 22d1889
22d1889 feat(marianos): enforce atomic generation checkpointing, azure blob failure rollback, auto-seeding input CSV, and explicit positive pickup fulfillment pricing
911b38e Update provenance manifest and checksums for implementation commit f9f63be28d4e31fb96b15f96aac1822bee524058
f9f63be Clarify ProcessDeadlineSupervisor parent-process separation, add indefinite pipe/file block regression, and verify PowerShell inherited-handle bounded drain and redaction
3f61781 Update provenance manifest and checksums for implementation commit 26eecbc0419a8bf7908eae39cf31eadf275b6cad
26eecbc Resolve Reviewer November 3 items: process supervisor separation, unblockable atomic receipt persistence, concurrent stream draining, process-tree termination, and credential redaction
1da3613 Update provenance manifest and checksums for implementation commit 00a4238
00a4238 Resolve Reviewer November 2 items: independent deadline supervisor, bounded CLI timeouts on all platforms, strict commit binding, and end-to-end orchestration integration tests
```

## 2. Deliverable File SHA-256 Checksums
Reviewers without access to Git CLI can independently verify that the deliverable files in this ZIP package exactly match the repository state using standard SHA-256 checksums:

| File Path | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `src/browser_engine.py` | 16726 | `68536faa63fb109d1612256f0781e5911efc61570b38c065bff69968aaa404b1` |
| `src/parser.py` | 22512 | `5ae509fbcddf11a67fb3cfc6922c4dc0083dd45ddba195ce75e287fbddc57ae4` |
| `src/storage_manager.py` | 38662 | `0ac7d29dcdb971ebd8270a3dc8942ab04b7f0102ec67316c319a95ea7f4e401c` |
| `src/config_loader.py` | 5693 | `33be218d2b9250754f67e39429d6fe82efe81ce91bfea68fdfb24cc27ad58a60` |
| `scripts/run_azure_bounded_probe.py` | 67362 | `af5ccb89356b5fa056c045bf0d5e0fde8b4c4e277acb735ddca23e31470b7596` |
| `azure/azure-deploy-bounded-probe.sh` | 19148 | `025266f0b3d668a50bb19c41ce570153aabb92a06c5504f5ccf9ff3ef184d437` |
| `azure/azure-deploy-bounded-probe.ps1` | 26956 | `01f59f522f22e4b8a8e4ecf55fbe580af848886c77226f9fb9b4d44dfcf53ae1` |
| `azure/azure-deploy.ps1` | 6371 | `2c09ad1156424d1d79103d01df72dd401cc3e4414b943c871d5048b477bd8ca5` |
| `azure/azure-deploy.sh` | 3337 | `a8ce3595d19f6e27d6c9f24201d2262a0f3409c1d540e110f8651d8b12666cc8` |
| `azure/Dockerfile` | 899 | `389b2a87c26d5e67f3ee758cb949d064b6cfd9cb7a744a803d7c47a6371ae77a` |
| `requirements.txt` | 164 | `905fa226e9977f3789881b762f845749d8679e74aa8aa1d58cb822688cfab9a6` |
| `config/locations.json` | 1747 | `41715044b6679a1b8f8e9ac568e7029c5997107febcd1a4fe939bb874ee21300` |
| `config/seeds/Marianos_Category_URLs.csv` | 6095 | `29ef0da05bc3e6d2a7b6eff036df02371052afa9bf6316b3c9fb546c81b09cc0` |
| `data/output/marianos_scraped_data_store_53100503_full_catalog.json` | 531736 | `4cf70cc481c7d7d5b44f09e4eb6447fdcaccc302cf0daf8e09e08745f2a6b386` |
| `data/output/marianos_contest_submission_500_records.json` | 474696 | `62ddcff33c8a5d98c7c572f7bb2e1410b443f5c195469055e3033d6ae4191c5f` |
| `data/output/marianos_audit_statistics.json` | 13844 | `59d162655151de68537f8f114a02953b4025b38de7c6d1ca60793fa366768a89` |
| `data/input/Marianos_Category_URLs.csv` | 6095 | `29ef0da05bc3e6d2a7b6eff036df02371052afa9bf6316b3c9fb546c81b09cc0` |
| `data/checkpoints/active_checkpoint_store_53100503.json` | 1944 | `5f504f9b69436774db8a23106807507cc3726bd24818fbb0afeea82ea5179aca` |
| `data/checkpoints/checkpoint_store_53100503.json` | 1636 | `a204b6b9af90719d6baff255ff528419ec5798749e9b4b3d9f910659009786ec` |
| `data/checkpoints/checkpoint_rows_store_53100503.jsonl` | 41527 | `74b19bc5fbb44101f506b1e7465ec6cfdad23c2b0f3d868d1500c08d03983c15` |
| `logs/source_to_output_reconciliation_audit.json` | 10614 | `5aa2ec89ccb1398b9f57cb41be17e1648b6ea5582a637860ad929ec0ae864d33` |

## 3. Remote Verification Link
The full commit history, diffs, and trees can be inspected directly on GitHub at:
`https://github.com/sohel369/Mariano-s-Scraper-For-Azure-Environment/tree/5ea61b8dbd5626cf0c9c17c6dbe71d2febf1c855`
