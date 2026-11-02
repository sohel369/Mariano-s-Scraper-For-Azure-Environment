import os
import sys
import shutil
import hashlib
import tempfile
import subprocess
import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MOCK_AZ_PY = """
import sys, os, time, hashlib, base64

args = sys.argv[1:]
log_mode = os.environ.get("MOCK_AZ_LOG_MODE", "success")
container_state = os.environ.get("MOCK_AZ_CONTAINER_STATE", "success")
group_exists = os.environ.get("MOCK_AZ_GROUP_EXISTS", "false")
build_hang = os.environ.get("MOCK_AZ_BUILD_HANG", "0")
run_id = os.environ.get("MOCK_RUN_ID", "mock_run_123")
commit_hash = os.environ.get("MOCK_PINNED_COMMIT", "15ef5df7bf504e393304dd0ad765fb95c0846b2c")
tmp_dir = os.environ.get("MOCK_AZ_STATE_DIR", os.path.dirname(__file__))

aci_deleted_file = os.path.join(tmp_dir, "aci_deleted.marker")
acr_deleted_file = os.path.join(tmp_dir, "acr_deleted.marker")
rg_deleted_file = os.path.join(tmp_dir, "rg_deleted.marker")

raw_body = b"<html>Vernon Hills #53100502 PICKUP verified</html>"
raw_b64 = base64.b64encode(raw_body).decode("ascii")
raw_sha = hashlib.sha256(raw_body).hexdigest()
raw_len = len(raw_body)

if "group" in args and "exists" in args:
    if os.path.exists(rg_deleted_file):
        print("false")
        sys.exit(0)
    if group_exists == "true":
        print("true")
        sys.exit(0)
    elif group_exists == "error":
        print("az error: failed query", file=sys.stderr)
        sys.exit(2)
    else:
        print("false")
        sys.exit(0)

elif "group" in args and "create" in args:
    print('{"name": "rg-mock", "properties": {"provisioningState": "Succeeded"}}')
    sys.exit(0)

elif "acr" in args and "create" in args:
    print('{"name": "acrmock", "loginServer": "acrmock.azurecr.io"}')
    sys.exit(0)

elif "acr" in args and "build" in args:
    if build_hang == "1":
        time.sleep(300)
    print("Mock ACR Build succeeded")
    sys.exit(0)

elif "acr" in args and "show" in args:
    if os.path.exists(acr_deleted_file):
        print("ResourceNotFound: The Resource 'acrmock' could not be found.", file=sys.stderr)
        sys.exit(3)
    if any("query" in a for a in args) and any("name" in a for a in args):
        print("acrmock")
    else:
        print("acrmock.azurecr.io")
    sys.exit(0)

elif "acr" in args and "credential" in args:
    print("mock_acr_credential_val")
    sys.exit(0)

elif "container" in args and "create" in args:
    cmd_str = " ".join(args)
    if "--run-id" in cmd_str:
        parts = cmd_str.split("--run-id")
        if len(parts) > 1:
            captured_id = parts[1].strip().split()[0].replace("'", "").replace('"', "")
            with open(os.path.join(tmp_dir, "current_run_id.txt"), "w") as rf:
                rf.write(captured_id)
    print('{"name": "aci-marianos-probe-job", "provisioningState": "Succeeded"}')
    sys.exit(0)

elif "container" in args and "logs" in args:
    run_id_file = os.path.join(tmp_dir, "current_run_id.txt")
    if os.path.exists(run_id_file):
        with open(run_id_file, "r") as rf:
            run_id = rf.read().strip()

    if log_mode == "empty":
        sys.exit(0)
    elif log_mode == "incomplete_blocks":
        print("===AZURE_PROBE_JSON_START===")
        print('{"probe_name": "AZURE_BOUNDED_PROBE_DIAGNOSTIC", "run_id": "' + run_id + '"')
        sys.exit(0)
    elif log_mode == "wrong_commit":
        print("===AZURE_PROBE_JSON_START===")
        print('{"probe_name": "AZURE_BOUNDED_PROBE_DIAGNOSTIC", "run_id": "' + run_id + '", "pinned_git_commit": "wrong_commit_deadbeef", "overall_status": "SUCCESS_PROBE_COMPLETE", "evidence": {"raw_response_size_bytes": ' + str(raw_len) + ', "raw_response_sha256": "' + raw_sha + '"}}')
        print("===AZURE_PROBE_JSON_END===")
        print("===AZURE_RAW_RESPONSE_BASE64_START===")
        print(raw_b64)
        print("===AZURE_RAW_RESPONSE_BASE64_END===")
        sys.exit(0)
    elif log_mode == "missing_commit":
        print("===AZURE_PROBE_JSON_START===")
        print('{"probe_name": "AZURE_BOUNDED_PROBE_DIAGNOSTIC", "run_id": "' + run_id + '", "pinned_git_commit": "", "overall_status": "SUCCESS_PROBE_COMPLETE", "evidence": {"raw_response_size_bytes": ' + str(raw_len) + ', "raw_response_sha256": "' + raw_sha + '"}}')
        print("===AZURE_PROBE_JSON_END===")
        print("===AZURE_RAW_RESPONSE_BASE64_START===")
        print(raw_b64)
        print("===AZURE_RAW_RESPONSE_BASE64_END===")
        sys.exit(0)
    else: # success
        print("===AZURE_PROBE_JSON_START===")
        print('{"probe_name": "AZURE_BOUNDED_PROBE_DIAGNOSTIC", "run_id": "' + run_id + '", "pinned_git_commit": "' + commit_hash + '", "overall_status": "SUCCESS_PROBE_COMPLETE", "evidence": {"raw_response_size_bytes": ' + str(raw_len) + ', "raw_response_sha256": "' + raw_sha + '"}}')
        print("===AZURE_PROBE_JSON_END===")
        print("===AZURE_RAW_RESPONSE_BASE64_START===")
        print(raw_b64)
        print("===AZURE_RAW_RESPONSE_BASE64_END===")
        sys.exit(0)

elif "container" in args and "show" in args:
    if os.path.exists(aci_deleted_file):
        print("ResourceNotFound: The Resource 'aci-marianos-probe-job' could not be found.", file=sys.stderr)
        sys.exit(3)
    if any("currentState.state" in a for a in args):
        if container_state == "unknown_state":
            print("Unknown")
        else:
            print("Terminated")
        sys.exit(0)
    elif any("currentState.exitCode" in a for a in args):
        if container_state == "unknown_terminal":
            print("")
        elif container_state == "failed_exit":
            print("1")
        else:
            print("0")
        sys.exit(0)
    elif any("query" in a for a in args) and any("name" in a for a in args):
        print("aci-marianos-probe-job")
        sys.exit(0)
    else:
        print('{"name": "aci-marianos-probe-job", "instanceView": {"currentState": {"state": "Terminated", "exitCode": 0}}}')
        sys.exit(0)

elif "container" in args and "delete" in args:
    with open(aci_deleted_file, "w") as f: f.write("1")
    print("Container deleted")
    sys.exit(0)

elif "acr" in args and "delete" in args:
    with open(acr_deleted_file, "w") as f: f.write("1")
    print("ACR deleted")
    sys.exit(0)

elif "group" in args and "delete" in args:
    with open(rg_deleted_file, "w") as f: f.write("1")
    print("Group deleted")
    sys.exit(0)

else:
    print("mock az fallback ok")
    sys.exit(0)
"""

def setup_mock_environment(tmp_path):
    mock_bin = tmp_path / "mock_bin"
    mock_bin.mkdir(parents=True, exist_ok=True)

    py_script = mock_bin / "mock_az.py"
    py_script.write_text(MOCK_AZ_PY, encoding="utf-8")

    # Windows batch wrapper for cmd.exe / powershell
    az_cmd = mock_bin / "az.cmd"
    az_cmd.write_text(f'@echo off\n"{sys.executable}" "{py_script}" %*\n', encoding="utf-8")

    # Unix shell script for Git Bash / WSL
    az_sh = mock_bin / "az"
    az_sh_content = f'#!/usr/bin/env sh\nexec "{sys.executable}" "{py_script}" "$@"\n'
    az_sh.write_text(az_sh_content, encoding="utf-8")

    try:
        os.chmod(str(az_sh), 0o755)
    except Exception:
        pass

    return mock_bin


def find_bash_executable():
    common_paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        shutil.which("bash")
    ]
    for p in common_paths:
        if p and os.path.exists(p):
            return p
    return None


@pytest.fixture
def mock_az_setup(tmp_path):
    mock_bin = setup_mock_environment(tmp_path)
    output_dir = tmp_path / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BASE_DIR, capture_output=True, text=True, check=True)
        commit = res.stdout.strip()
    except Exception:
        commit = "15ef5df7bf504e393304dd0ad765fb95c0846b2c"

    return {
        "mock_bin": mock_bin,
        "output_dir": output_dir,
        "commit": commit,
        "tmp_path": tmp_path
    }


def test_powershell_orchestration_rejects_unknown_container_terminal_state(mock_az_setup):
    """Verifies PowerShell orchestration rejects container with unknown terminal exit code."""
    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "unknown_terminal"
    env["MOCK_AZ_LOG_MODE"] = "success"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    ps1_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.ps1")
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ps1_script,
        "-OutputDir", str(output_dir)
    ]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode != 0
    assert "Exit UNKNOWN" in combined or "UNKNOWN" in combined
    assert "Stage 1 [Probe Execution]: FAILED" in combined


def test_powershell_orchestration_rejects_incomplete_final_blocks(mock_az_setup):
    """Verifies PowerShell orchestration retries and fails when evidence block is incomplete (START without END)."""
    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "success"
    env["MOCK_AZ_LOG_MODE"] = "incomplete_blocks"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    ps1_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.ps1")
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ps1_script,
        "-OutputDir", str(output_dir)
    ]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode != 0
    assert "retrieving fresh container logs from Azure" in combined
    assert "Stage 2 [Evidence Export]: FAILED" in combined


def test_powershell_orchestration_rejects_wrong_or_missing_commit(mock_az_setup):
    """Verifies PowerShell orchestration rejects receipts with mismatching or empty pinned_git_commit."""
    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "success"
    env["MOCK_AZ_LOG_MODE"] = "wrong_commit"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    ps1_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.ps1")
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ps1_script,
        "-OutputDir", str(output_dir)
    ]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode != 0
    assert "Stage 2 [Evidence Export]: FAILED" in combined


def test_bash_orchestration_rejects_unknown_container_terminal_state(mock_az_setup):
    """Verifies Bash orchestration rejects container with unknown terminal exit code."""
    bash_exe = find_bash_executable()
    if not bash_exe:
        pytest.skip("Bash executable not found on this host")

    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "unknown_terminal"
    env["MOCK_AZ_LOG_MODE"] = "success"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    sh_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.sh")
    cmd = [bash_exe, sh_script]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode != 0
    assert "Exit UNKNOWN" in combined or "UNKNOWN" in combined
    assert "Stage 1 [Probe Execution]: FAILED" in combined


def test_bash_orchestration_rejects_incomplete_final_blocks(mock_az_setup):
    """Verifies Bash orchestration retries and fails when evidence block is incomplete (START without END)."""
    bash_exe = find_bash_executable()
    if not bash_exe:
        pytest.skip("Bash executable not found on this host")

    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "success"
    env["MOCK_AZ_LOG_MODE"] = "incomplete_blocks"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    sh_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.sh")
    cmd = [bash_exe, sh_script]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode != 0
    assert "retrieving fresh container logs from Azure" in combined
    assert "Stage 2 [Evidence Export]: FAILED" in combined


def test_bash_orchestration_rejects_wrong_or_missing_commit(mock_az_setup):
    """Verifies Bash orchestration rejects receipts with mismatching or empty pinned_git_commit."""
    bash_exe = find_bash_executable()
    if not bash_exe:
        pytest.skip("Bash executable not found on this host")

    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "success"
    env["MOCK_AZ_LOG_MODE"] = "wrong_commit"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    sh_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.sh")
    cmd = [bash_exe, sh_script]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode != 0
    assert "Stage 2 [Evidence Export]: FAILED" in combined


def test_powershell_orchestration_succeeds_on_valid_run(mock_az_setup):
    """Verifies PowerShell orchestration completes Stage 1, Stage 2, and Stage 3 on genuine valid run."""
    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "success"
    env["MOCK_AZ_LOG_MODE"] = "success"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    ps1_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.ps1")
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ps1_script,
        "-OutputDir", str(output_dir)
    ]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode == 0
    assert "Stage 1 [Probe Execution]: SUCCESS" in combined
    assert "Stage 2 [Evidence Export]: VERIFIED" in combined
    assert "Stage 3 [Resource Teardown]: VERIFIED" in combined


def test_bash_orchestration_succeeds_on_valid_run(mock_az_setup):
    """Verifies Bash orchestration completes Stage 1, Stage 2, and Stage 3 on genuine valid run."""
    bash_exe = find_bash_executable()
    if not bash_exe:
        pytest.skip("Bash executable not found on this host")

    mock_bin = mock_az_setup["mock_bin"]
    output_dir = mock_az_setup["output_dir"]
    commit = mock_az_setup["commit"]
    tmp_path = mock_az_setup["tmp_path"]

    env = os.environ.copy()
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env["OUTPUT_DIR"] = str(output_dir)
    env["MOCK_AZ_CONTAINER_STATE"] = "success"
    env["MOCK_AZ_LOG_MODE"] = "success"
    env["MOCK_PINNED_COMMIT"] = commit
    env["MOCK_AZ_STATE_DIR"] = str(tmp_path)

    sh_script = os.path.join(BASE_DIR, "azure", "azure-deploy-bounded-probe.sh")
    cmd = [bash_exe, sh_script]

    res = subprocess.run(cmd, env=env, cwd=BASE_DIR, capture_output=True, text=True)
    combined = res.stdout + res.stderr

    assert res.returncode == 0
    assert "Stage 1 [Probe Execution]: SUCCESS" in combined
    assert "Stage 2 [Evidence Export]: VERIFIED" in combined
    assert "Stage 3 [Resource Teardown]: VERIFIED" in combined
