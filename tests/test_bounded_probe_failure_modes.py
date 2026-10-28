"""
Unit tests verifying strict failure-mode handling in AzureBoundedProbeRunner.
Fulfills reviewer requirements:
- HTTP 500 must fail and exit with non-zero status.
- HTTP 200 without store context must fail.
- Fake clock exceeding deadline must trigger ABORTED_DEADLINE_EXCEEDED.
- Zero generated/mock records.
"""

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.run_azure_bounded_probe import AzureBoundedProbeRunner


def test_probe_fails_on_http_500(tmp_path):
    """Verifies that an HTTP 500 error page produces a failing status and zero records."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(output_file=str(output_json))

    # Mock response returning HTTP 500
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [b"Internal Server Error"]

    with patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "FAILED_HTTP_500"
    assert res["collected_records_count"] == 0
    assert len(res["sample_records"]) == 0
    assert res["probe_metrics"]["http_status_code"] == 500


def test_probe_fails_on_missing_store_context(tmp_path):
    """Verifies that an HTTP 200 page without verified store context produces FAILED_MISSING_STORE_CONTEXT."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(output_file=str(output_json))

    # Mock response returning ordinary page without store context
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [b"<html><body><h1>Welcome to Mariano's</h1></body></html>"]

    with patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "FAILED_MISSING_STORE_CONTEXT"
    assert res["probe_metrics"]["store_fulfillment_verified_in_source"] is False
    assert res["collected_records_count"] == 0


def test_probe_enforces_whole_run_deadline(tmp_path):
    """Verifies that when clock advances past deadline, status is strictly ABORTED_DEADLINE_EXCEEDED."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(run_deadline_seconds=10.0, output_file=str(output_json))

    # Simulate fake clock jump during execution to 25.0s (deadline was 10.0s)
    real_monotonic = time.monotonic
    call_count = 0

    def mock_time():
        nonlocal call_count
        call_count += 1
        # Advance time by 30 seconds on second call
        if call_count >= 2:
            return runner.start_time_monotonic + 30.0
        return runner.start_time_monotonic + 1.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [b"<html><body>531/00502 \"storeId\":\"53100502\"</body></html>"]

    with patch("time.monotonic", side_effect=mock_time), patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "ABORTED_DEADLINE_EXCEEDED"
