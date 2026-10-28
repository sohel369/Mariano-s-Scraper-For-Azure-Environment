import os
import json
import hashlib
import subprocess
from datetime import datetime, timezone

def get_file_sha256(filepath):
    if not os.path.exists(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def run_git(cmd):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"

def generate_provenance():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    head_hash = run_git(["git", "rev-parse", "HEAD"])
    branch = run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    remote_url = run_git(["git", "config", "--get", "remote.origin.url"])
    recent_logs = run_git(["git", "log", "-n", "8", "--oneline"]).splitlines()
    status_short = run_git(["git", "status", "--short"])
    
    tracked_files = [
        "scripts/run_azure_bounded_probe.py",
        "azure/azure-deploy-bounded-probe.sh",
        "azure/azure-deploy-bounded-probe.ps1",
        "azure/Dockerfile",
        "requirements.txt",
        "config/locations.json",
        "data/output/marianos_scraped_data_store_53100503_full_catalog.json",
        "data/output/marianos_contest_submission_500_records.json",
        "data/output/marianos_audit_statistics.json",
        "data/input/Marianos_Category_URLs_Original_Brief.csv",
        "data/input/Marianos_Category_URLs.csv",
        "logs/category_route_mapping_structure_audit.json",
        "logs/missing_route_rejection_audit_proof.json"
    ]
    
    file_hashes = {}
    for rel in tracked_files:
        full = os.path.join(base_dir, rel)
        file_hashes[rel] = {
            "exists": os.path.exists(full),
            "size_bytes": os.path.getsize(full) if os.path.exists(full) else 0,
            "sha256": get_file_sha256(full)
        }
        
    provenance = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "git_repository": remote_url,
        "branch": branch,
        "head_commit": head_hash,
        "working_tree_clean": (len(status_short) == 0),
        "recent_commits": recent_logs,
        "file_sha256_checksums": file_hashes
    }
    
    # Save machine-readable JSON
    proof_json = os.path.join(base_dir, "logs", "git_commit_lineage_proof.json")
    os.makedirs(os.path.dirname(proof_json), exist_ok=True)
    with open(proof_json, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)
    print(f"Saved JSON proof: {proof_json}")
    
    # Save human-readable markdown
    md_content = f"""# GIT PROVENANCE & FILE INTEGRITY MANIFEST

**Generated UTC:** {provenance['generated_utc']}  
**Repository URL:** [{remote_url}]({remote_url})  
**Branch:** `{branch}`  
**HEAD Commit:** `{head_hash}`  
**Working Tree Clean:** `{provenance['working_tree_clean']}`  

## 1. Recent Authoritative Commits
```text
""" + "\n".join(recent_logs) + f"""
```

## 2. Deliverable File SHA-256 Checksums
Reviewers without access to Git CLI can independently verify that the deliverable files in this ZIP package exactly match the repository state using standard SHA-256 checksums:

| File Path | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
"""
    for rel, meta in file_hashes.items():
        md_content += f"| `{rel}` | {meta['size_bytes']} | `{meta['sha256']}` |\n"
        
    md_content += f"""
## 3. Remote Verification Link
The full commit history, diffs, and trees can be inspected directly on GitHub at:
`{remote_url.replace('.git', '')}/tree/{head_hash}`
"""

    md_file = os.path.join(base_dir, "GIT_PROVENANCE_AND_INTEGRITY.md")
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved Markdown proof: {md_file}")

if __name__ == "__main__":
    generate_provenance()
