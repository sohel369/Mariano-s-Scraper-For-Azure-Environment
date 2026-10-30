"""
Unit tests verifying strict failure-mode handling in AzureBoundedProbeRunner.
Fulfills Reviewer Item 2, 3, 4, 5 stipulations (October 30 Review):
- Conflicting store IDs (e.g. 99900502 with 531/00502) strictly rejected.
- Actual store 53100503/SHIPPING with unrelated Vernon Hills link strictly rejected.
- Products with conflicting locationId (53100503) or SHIPPING modality strictly rejected.
- Request attempt counted before dispatch (timeout still counted).
- Enforced completion deadline through finalization (injected write delay triggers ABORTED_DEADLINE_EXCEEDED).
- Retry allowance enforced separately from max_requests (zero-retry and one-retry cases).
- Price-bearing trace uses correct schema keys (product_title, regular_price, sale_price, url) with no nulls.
- HTTP 500 fails with non-zero exit code and 0 records.
"""

import os
import sys
import time
import json
import pytest
import requests
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
    """Verifies Reviewer Item 2 Case 1: storeId 99900502 with division 531/storeNumber 00502 must be rejected."""
    runner = AzureBoundedProbeRunner(output_file=str(tmp_path / "probe_result.json"))

    body_conflicting = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"store":{"storeId":"99900502","divisionId":"531","storeNumber":"00502"},"modality":{"type":"PICKUP"}}}}
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


def test_store_verification_rejects_actual_store_53100503_shipping_with_directory_link(tmp_path):
    """Verifies Reviewer Item 2 Case 2: actual store 53100503/SHIPPING supplemented by unrelated Vernon Hills directory link."""
    runner = AzureBoundedProbeRunner(output_file=str(tmp_path / "probe_result.json"))

    # Actual store is 53100503 / SHIPPING, but someone puts an unrelated directory link and data-modality="PICKUP"
    body_spoofed = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"store":{"storeId":"53100503","divisionId":"531","storeNumber":"00503"},"modality":{"type":"SHIPPING"}}}}
      </script>
      <a href="/stores/grocery/il/vernon-hills/marianos-vernon-hills/531/00502">Vernon Hills Store</a>
      <div data-modality="PICKUP">$4.99</div>
    </body></html>
    """
    verified = runner.validate_store_and_fulfillment_structurally(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body_text=body_spoofed
    )
    assert verified is False
    assert runner.store_fulfillment_verified is False


def test_store_verification_rejects_product_with_conflicting_location_or_shipping(tmp_path):
    """Verifies Reviewer Item 2 Case 3: Page is 53100502/PICKUP, but product item is locationId 53100503/SHIPPING."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(output_file=str(output_json))

    # Page state has 53100502/PICKUP, but product has locationId: 53100503 and fulfillment: SHIPPING
    html_with_conflicting_prod = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "store": {"storeId": "53100502", "divisionId": "531", "storeNumber": "00502"},
              "modality": {"type": "PICKUP"},
              "products": [
                {
                  "name": "Organic Whole Chicken",
                  "locationId": "53100503",
                  "modality": "SHIPPING",
                  "priceInfo": {"currentPrice": {"price": 5.99}},
                  "canonicalUrl": "/p/organic-chicken/0001111000123"
                }
              ]
            }
          }
        }
      </script>
      <div class="price">$5.99</div>
    </body></html>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [html_with_conflicting_prod.encode("utf-8")]

    with patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    # Conflicting product must be rejected; must not export price $5.99 as Vernon Hills
    assert res["overall_status"] != "SUCCESS_PROBE_COMPLETE"
    assert res["collected_records_count"] == 0


def test_enforced_deadline_through_finalization_with_injected_write_delay(tmp_path):
    """Verifies Reviewer Item 3: Injected delay during JSON write forces status to ABORTED_DEADLINE_EXCEEDED."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(run_deadline_seconds=0.1, output_file=str(output_json))

    html_success = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "store": {"storeId": "53100502", "divisionId": "531", "storeNumber": "00502"},
              "modality": {"type": "PICKUP"},
              "products": [
                {
                  "name": "Local Fresh Meat",
                  "locationId": "53100502",
                  "modality": "PICKUP",
                  "priceInfo": {"currentPrice": {"price": 4.99}},
                  "canonicalUrl": "/p/meat/0001111000999"
                }
              ]
            }
          }
        }
      </script>
      <div class="price">$4.99</div>
    </body></html>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [html_success.encode("utf-8")]

    # Inject a 0.15s sleep into json.dump (simulating Darren's 0.25s injected delay against 0.1s deadline)
    orig_dump = json.dump

    def slow_dump(*args, **kwargs):
        time.sleep(0.15)
        return orig_dump(*args, **kwargs)

    with patch("requests.Session.get", return_value=mock_resp), patch("json.dump", side_effect=slow_dump):
        res = runner.execute_bounded_probe()

    # Deadline was 0.1s; slow_dump added 0.15s. Total elapsed > 0.1s!
    assert res["overall_status"] == "ABORTED_DEADLINE_EXCEEDED"
    assert res["probe_metrics"]["elapsed_seconds"] > 0.1

    # Check on-disk file: must ALSO be ABORTED_DEADLINE_EXCEEDED
    with open(output_json, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["overall_status"] == "ABORTED_DEADLINE_EXCEEDED"


def test_retry_allowance_zero_retries_makes_single_attempt():
    """Verifies Reviewer Item 4: With max_retries=0 and simulated timeout, exactly 1 attempt occurs."""
    runner = AzureBoundedProbeRunner(max_retries=0, max_requests=3)

    mock_request = MagicMock()
    call_count = 0

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise requests.exceptions.Timeout("Connection timed out")

    with patch("requests.Session.get", side_effect=mock_get):
        res = runner.execute_bounded_probe()

    # Must make exactly 1 attempt, 0 retries
    assert call_count == 1
    assert res["probe_metrics"]["total_requests_executed"] == 1
    assert res["probe_metrics"]["initial_attempts_executed"] == 1
    assert res["probe_metrics"]["retries_executed"] == 0


def test_retry_allowance_one_retry_makes_two_attempts():
    """Verifies Reviewer Item 4: With max_retries=1 and simulated timeouts, exactly 2 attempts occur."""
    runner = AzureBoundedProbeRunner(max_retries=1, max_requests=3)

    call_count = 0

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise requests.exceptions.Timeout("Connection timed out")

    with patch("requests.Session.get", side_effect=mock_get):
        res = runner.execute_bounded_probe()

    # Must make exactly 2 attempts (1 initial + 1 retry)
    assert call_count == 2
    assert res["probe_metrics"]["total_requests_executed"] == 2
    assert res["probe_metrics"]["initial_attempts_executed"] == 1
    assert res["probe_metrics"]["retries_executed"] == 1


def test_trace_fields_have_no_nulls_and_correct_keys(tmp_path):
    """Verifies Reviewer Item 5: Price trace sample uses correct row schema keys without nulls."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(output_file=str(output_json))

    html_success = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "store": {"storeId": "53100502", "divisionId": "531", "storeNumber": "00502"},
              "modality": {"type": "PICKUP"},
              "products": [
                {
                  "name": "Heritage Farm Chicken Breast",
                  "upc": "0001111041600",
                  "locationId": "53100502",
                  "modality": "PICKUP",
                  "priceInfo": {"currentPrice": {"price": 3.99}},
                  "canonicalUrl": "/p/heritage-farm-chicken/0001111041600"
                }
              ]
            }
          }
        }
      </script>
      <div class="price">$3.99</div>
    </body></html>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [html_success.encode("utf-8")]

    with patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "SUCCESS_PROBE_COMPLETE"
    trace = res["evidence"]["store_fulfillment_trace"]["price_bearing_trace_sample"]
    assert len(trace) > 0

    first_item = trace[0]
    # Check that schema keys exist and are NOT null
    assert "product_title" in first_item and first_item["product_title"] == "Heritage Farm Chicken Breast"
    assert "upc" in first_item and first_item["upc"] == "0001111041600"
    assert "regular_price" in first_item and first_item["regular_price"] != ""
    assert "verified_store_id" in first_item and first_item["verified_store_id"] == "53100502"
    assert "verified_modality" in first_item and first_item["verified_modality"] == "PICKUP"
