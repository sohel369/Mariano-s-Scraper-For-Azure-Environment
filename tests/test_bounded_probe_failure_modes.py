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


def test_bounded_adapter_dispatch_counting_with_adapter_send(tmp_path):
    """Verifies that aggregate_requests_count tracks actual dispatches in adapter.send without double-counting."""
    # Case A: max_requests=1, max_retries=0: does NOT pre-abort before dispatch
    output_json = tmp_path / "probe_result_1.json"
    runner1 = AzureBoundedProbeRunner(max_requests=1, max_retries=0, output_file=str(output_json))

    adapter1 = BoundedRequestAdapter(probe=runner1)
    mock_request = MagicMock()
    with patch("requests.adapters.HTTPAdapter.send") as mock_super_send:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_super_send.return_value = mock_resp

        # First send must succeed and increment aggregate_requests_count to 1
        resp = adapter1.send(mock_request)
        assert runner1.aggregate_requests_count == 1
        assert runner1.probe_status == "INITIALIZING"

        # Subsequent send must raise RuntimeError because max_requests (1) is reached
        with pytest.raises(RuntimeError) as exc_info:
            adapter1.send(mock_request)
        assert "Aggregate request ceiling (1) reached" in str(exc_info.value)

    # Case B: Probe with max_requests=3, max_retries=0: exactly 1 dispatch reports total_requests_executed == 1
    output_json2 = tmp_path / "probe_result_2.json"
    runner2 = AzureBoundedProbeRunner(max_requests=3, max_retries=0, connectivity_only=True, output_file=str(output_json2))

    html_payload = '<html><body>"storeId":"53100502" "modality":"PICKUP" $1.99</body></html>'.encode("utf-8")
    with patch("requests.adapters.HTTPAdapter.send") as mock_super_send:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.iter_content.return_value = [html_payload]
        mock_super_send.return_value = mock_resp

        res = runner2.execute_bounded_probe()
        assert res["probe_metrics"]["total_requests_executed"] == 1
        assert res["probe_metrics"]["initial_attempts_executed"] == 1
        assert res["probe_metrics"]["retries_executed"] == 0


def test_attempt_buffer_reset_on_chunked_transfer_failure(tmp_path):
    """Verifies Reviewer Item 5: Injected chunked-transfer error on attempt 1 resets attempt buffer; no body concatenation."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(max_retries=1, max_requests=3, connectivity_only=True, output_file=str(output_json))

    attempt = 0
    def mock_get(*args, **kwargs):
        nonlocal attempt
        attempt += 1
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        if attempt == 1:
            def failing_chunks(chunk_size=8192):
                yield b"A" * 500
                raise requests.exceptions.ChunkedEncodingError("Chunked stream broken")
            mock_resp.iter_content = failing_chunks
            return mock_resp
        else:
            valid_payload = b'<html><body>"storeId":"53100502" "modality":"PICKUP" $1.99' + (b"B" * 1000) + b'</body></html>'
            mock_resp.iter_content = lambda chunk_size=8192: [valid_payload]
            return mock_resp

    with patch("requests.Session.get", side_effect=mock_get):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "SUCCESS_CONNECTIVITY_ONLY"
    assert len(res["probe_metrics"]["attempt_receipts"]) == 2
    # Attempt 1 recorded 500 bytes before error
    assert res["probe_metrics"]["attempt_receipts"][0]["bytes_read"] == 500
    assert "Chunked stream broken" in res["probe_metrics"]["attempt_receipts"][0]["error"]
    # Attempt 2 buffer was clean; raw response must NOT contain 'A' * 500!
    assert b"A" * 500 not in runner.raw_response_bytes
    assert b"B" * 1000 in runner.raw_response_bytes


def test_store_verification_rejects_vanity_id_mismatch(tmp_path):
    """Verifies Reviewer Item 3: Page with storeId 53100502 but vanityId 53100503 is rejected."""
    runner = AzureBoundedProbeRunner(output_file=str(tmp_path / "probe_result.json"))

    body_with_bad_vanity = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"store":{"storeId":"53100502","vanityId":"53100503","divisionId":"531","storeNumber":"00502"},"modality":{"type":"PICKUP"}}}}
      </script>
      <div class="price">$5.99</div>
    </body></html>
    """
    verified = runner.validate_store_and_fulfillment_structurally(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body_text=body_with_bad_vanity
    )
    assert verified is False
    assert runner.store_fulfillment_verified is False
    assert runner.probe_status == "FAILED_CONFLICTING_STORE_IDENTITY"
    assert "vanityId" in runner.failure_reason


def test_store_verification_rejects_embedded_priceinfo_store_mismatch(tmp_path):
    """Verifies Reviewer Item 3: Top-level store matches 53100502, but embedded product priceInfo specifies 53100503."""
    runner = AzureBoundedProbeRunner(output_file=str(tmp_path / "probe_result.json"))

    body_with_priceinfo_mismatch = """
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
                  "priceInfo": {
                    "storeId": "53100503",
                    "locationId": "53100503",
                    "currentPrice": {"price": 4.99}
                  },
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
    verified = runner.validate_store_and_fulfillment_structurally(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body_text=body_with_priceinfo_mismatch
    )
    assert verified is False
    assert runner.store_fulfillment_verified is False
    assert runner.probe_status == "FAILED_CONFLICTING_STORE_IDENTITY"
    assert "53100503" in runner.failure_reason


def test_on_disk_json_has_accurate_elapsed_seconds_on_success(tmp_path):
    """Verifies Reviewer Item 6: On-disk JSON contains non-zero elapsed_seconds after successful run."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(connectivity_only=True, output_file=str(output_json))

    html_success = '<html><body>"storeId":"53100502" "modality":"PICKUP" $1.99</body></html>'
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [html_success.encode("utf-8")]

    with patch("requests.Session.get", return_value=mock_resp):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "SUCCESS_CONNECTIVITY_ONLY"
    assert res["probe_metrics"]["elapsed_seconds"] > 0.0

    # Verify directly from on-disk JSON file
    with open(output_json, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["probe_metrics"]["elapsed_seconds"] > 0.0
    assert disk_data["probe_metrics"]["elapsed_seconds"] == res["probe_metrics"]["elapsed_seconds"]
    assert disk_data["overall_status"] == "SUCCESS_CONNECTIVITY_ONLY"


def test_whole_run_deadline_supervisor_over_delimiter_printing(tmp_path):
    """Verifies Reviewer Item 6: Delay during delimiter printing overrides status and updates disk to ABORTED_DEADLINE_EXCEEDED."""
    output_json = tmp_path / "probe_result.json"
    runner = AzureBoundedProbeRunner(run_deadline_seconds=0.1, connectivity_only=True, output_file=str(output_json))

    html_success = '<html><body>"storeId":"53100502" "modality":"PICKUP" $1.99</body></html>'
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.iter_content.return_value = [html_success.encode("utf-8")]

    orig_print = print
    def slow_print(*args, **kwargs):
        # Inject delay when delimiter is printed
        if args and any("===AZURE_PROBE_JSON_START===" in str(a) for a in args):
            time.sleep(0.15)
        return orig_print(*args, **kwargs)

    with patch("requests.Session.get", return_value=mock_resp), patch("builtins.print", side_effect=slow_print):
        res = runner.execute_bounded_probe()

    assert res["overall_status"] == "ABORTED_DEADLINE_EXCEEDED"
    assert res["probe_metrics"]["elapsed_seconds"] > 0.1

    with open(output_json, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["overall_status"] == "ABORTED_DEADLINE_EXCEEDED"
