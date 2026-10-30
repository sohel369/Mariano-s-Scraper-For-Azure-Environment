"""
Unit tests verifying strict failure-mode handling in AzureBoundedProbeRunner.
Fulfills Reviewer Item 2 and Item 3 stipulations (October 29 Review):
- Conflicting store IDs (e.g. 99900502) strictly rejected.
- Absent/empty modality strictly rejected (explicit 'PICKUP' required).
- Cookie-only evidence without price-bearing context strictly rejected.
- Request attempt counted before dispatch (timeout still counted).
- Constructor strictly clamps ceilings (max 3 requests, max 60.0s deadline).
- HTTP 500 fails with non-zero exit code and 0 records.
- Fake clock exceeding deadline triggers ABORTED_DEADLINE_EXCEEDED.
"""

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.run_azure_bounded_probe import AzureBoundedProbeRunner, BoundedRequestAdapter


def test_probe_fails_on_http_500(tmp_path):
    """Verifies that an HTTP 500 error page produces a failing status and zero records."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(output_file=str(output_json))

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [b"Internal Server Error"]

    with patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "FAILED_HTTP_500"
    assert res["collected_records_count"] == 0
    assert len(res["collected_records"]) == 0
    assert res["probe_metrics"]["http_status_code"] == 500


def test_probe_fails_on_missing_store_context(tmp_path):
    """Verifies that an HTTP 200 page without verified store context produces FAILED_MISSING_STORE_CONTEXT."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(output_file=str(output_json))

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

    call_count = 0

    def mock_time():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            return runner.start_time_monotonic + 30.0
        return runner.start_time_monotonic + 1.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [b"<html><body>531/00502 \"storeId\":\"53100502\" $1.99</body></html>"]

    with patch("time.monotonic", side_effect=mock_time), patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "ABORTED_DEADLINE_EXCEEDED"


def test_store_verification_rejects_conflicting_id(tmp_path):
    """Verifies Item 2 requirement: Conflicting store ID 99900502 must be rejected."""
    runner = AzureBoundedProbeRunner(output_file=str(tmp_path / "probe_result.json"))

    body_conflicting = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"store":{"storeId":"99900502","divisionId":"999","storeNumber":"99900502"},"modality":{"type":"PICKUP"}}}}
      </script>
      <div class="price">$5.99</div>
    </body></html>
    """
    verified = runner.validate_store_and_fulfillment_structurally(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body_text=body_conflicting
    )
    assert verified is False
    assert runner.store_fulfillment_verified is False


def test_store_verification_rejects_absent_modality(tmp_path):
    """Verifies Item 2 requirement: Absent or empty modality must be rejected."""
    runner = AzureBoundedProbeRunner(output_file=str(tmp_path / "probe_result.json"))

    # Store ID is correct (53100502), but modality is absent/empty
    body_no_modality = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"store":{"storeId":"53100502","divisionId":"531","storeNumber":"00502"},"modality":{}}}}
      </script>
      <div class="price">$5.99</div>
    </body></html>
    """
    verified = runner.validate_store_and_fulfillment_structurally(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body_text=body_no_modality
    )
    assert verified is False
    assert runner.store_fulfillment_verified is False


def test_store_verification_rejects_cookie_only_evidence(tmp_path):
    """Verifies Item 2 requirement: Cookie-only evidence without price-bearing context must be rejected."""
    runner = AzureBoundedProbeRunner(output_file=str(tmp_path / "probe_result.json"))

    headers_with_cookies = {
        "set-cookie": "kroger.storeId=53100502; Path=/; kroger.modality=PICKUP; Path=/"
    }
    body_no_price_context = "<html><body><h1>Search Results</h1><p>No products available</p></body></html>"

    verified = runner.validate_store_and_fulfillment_structurally(
        status_code=200,
        headers=headers_with_cookies,
        body_text=body_no_price_context
    )
    assert verified is False
    assert runner.store_fulfillment_verified is False


def test_adapter_counts_attempts_before_dispatch_on_timeout():
    """Verifies Item 3 requirement: Attempt counter increments before network dispatch even on timeout."""
    runner = AzureBoundedProbeRunner(max_requests=3)
    adapter = BoundedRequestAdapter(probe=runner)

    assert runner.aggregate_requests_count == 0

    mock_request = MagicMock()
    # Simulate timeout inside super().send
    with patch("requests.adapters.HTTPAdapter.send", side_effect=Exception("Read timed out")):
        with pytest.raises(Exception):
            adapter.send(mock_request)

    # Counter MUST have incremented to 1 before dispatch
    assert runner.aggregate_requests_count == 1

    # Second timeout attempt
    with patch("requests.adapters.HTTPAdapter.send", side_effect=Exception("Read timed out")):
        with pytest.raises(Exception):
            adapter.send(mock_request)

    assert runner.aggregate_requests_count == 2


def test_constructor_enforces_strict_plan_ceilings():
    """Verifies Item 3 requirement: Constructor cannot be initialized with wider limits than plan."""
    runner = AzureBoundedProbeRunner(
        max_requests=10,            # Proposed ceiling: 3
        run_deadline_seconds=120.0, # Proposed ceiling: 60.0
        max_records_override=50     # Proposed ceiling: 20
    )
    assert runner.max_requests == 3
    assert runner.run_deadline_seconds == 60.0
    assert runner.max_records_override == 20
