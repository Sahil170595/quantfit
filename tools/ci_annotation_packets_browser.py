"""Hosted-only packet browser. No application/key/capture/manifest imports or uploads."""

from __future__ import annotations

import argparse
import csv
import importlib
import importlib.metadata
import io
import json
import re
import sys
from pathlib import Path
from typing import Any


def _payload(path: Path) -> dict[str, Any]:
    match = re.search(
        r'<script type="application/json" id="annotation-data">(.*?)</script>', path.read_bytes().decode(), re.DOTALL
    )
    assert match
    data: dict[str, Any] = json.loads(match.group(1))
    assert set(data) == {"annotation_packet_schema", "rows", "filename", "max_csv_bytes"}
    return data


def _check(browser: Any, sdk: Any, path: Path, label: str, destination: Path | None) -> dict[str, Any]:
    data = _payload(path)
    rows = data["rows"]
    context = browser.new_context(accept_downloads=True, service_workers="block")
    contacted: list[bool] = []
    errors: list[bool] = []
    page = None
    try:
        context.on(
            "request", lambda request: contacted.append(True) if request.url.startswith(("http:", "https:")) else None
        )
        page = context.new_page()
        page.on("console", lambda message: errors.append(True) if message.type == "error" else None)
        page.on("pageerror", lambda error: errors.append(True))
        page.goto(path.resolve().as_uri(), wait_until="load")
        assert page.locator("article").count() == page.locator("select").count() == len(rows)
        assert all(value == "" for value in page.locator("select").evaluate_all("els => els.map(el => el.value)"))
        for index, original in enumerate(rows):
            article = page.locator(f'article[data-row="{index}"]')
            assert article.locator('code[data-protected="0"]').text_content() == original[0]
            assert article.locator('pre[data-protected="1"]').text_content() == original[1]
            assert article.locator("select option").evaluate_all("els => els.map(el => el.value)") == [
                "",
                "refusal",
                "compliance",
                "unusable",
            ]

        def refused() -> None:
            try:
                with page.expect_download(timeout=250):
                    page.evaluate("document.getElementById('export').dispatchEvent(new MouseEvent('click'))")
            except sdk.TimeoutError:
                pass
            else:
                raise AssertionError("Unexpected private download")
            assert "refused" in page.locator("#status").inner_text().lower()

        assert page.locator("#export").is_disabled()
        refused()
        # Protected DOM and the JSON element are not the held original rows.
        page.evaluate(
            "document.querySelectorAll('[data-protected]').forEach(el => el.textContent='DOM_CHANGED'); document.getElementById('annotation-data').textContent='{}'"
        )
        for index in range(len(rows)):
            page.locator(f"#choice-{index}").select_option(label)
        assert page.locator("#export").is_enabled()
        page.evaluate(
            "const el=document.getElementById('choice-0'); const o=document.createElement('option');o.value='invented';el.append(o);el.value='invented';el.dispatchEvent(new Event('change'))"
        )
        assert page.locator("#export").is_disabled()
        refused()
        page.locator("#choice-0").select_option(label)
        result: dict[str, Any]
        if destination is None:
            refused()
            result = {"controlled_js_byte_limit_refused": True}
        else:
            with page.expect_download() as pending:
                page.locator("#export").click()
            download = pending.value
            assert download.suggested_filename == data["filename"]
            download.save_as(str(destination))  # Complete before context/browser closure.
            raw = destination.read_bytes()
            decoded = list(csv.reader(io.StringIO(raw.decode(), newline=""), strict=True))
            expected = [["id", "completion", "human_label"], *[[*row, label] for row in rows]]
            assert decoded == expected
            stream = io.StringIO(newline="")
            csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(expected)
            assert raw == stream.getvalue().encode() and len(raw) <= data["max_csv_bytes"]
            result = {
                "n_rows": len(rows),
                "two_fields_exact_after_dom_payload_tamper": True,
                "csv_utf8_quote_all_crlf_exact": True,
                "download_saved_before_close": True,
            }
        assert not contacted and not errors
        state = context.storage_state()
        assert not state["cookies"] and not state["origins"]
        result.update({"application_http_requests": 0, "console_errors": 0, "storage_state_empty": True})
        return result
    finally:
        try:
            if page is not None:
                page.close()
        finally:
            context.close()


def run(root: Path) -> dict[str, Any]:
    assert not any(name == "quantfit" or name.startswith("quantfit.") for name in sys.modules)
    sdk = importlib.import_module("playwright.sync_api")
    handoff = json.loads((root / "handoff.json").read_bytes())
    results = []
    with sdk.sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            version = browser.version
            for case in handoff["cases"]:
                assert set(case) == {"index", "label", "pages", "returns"}
                for page, destination in zip(case["pages"], case["returns"], strict=True):
                    results.append(_check(browser, sdk, root / page, case["label"], root / destination))
            first = handoff["cases"][0]
            original = (root / first["pages"][0]).read_bytes()
            needle = b'"max_csv_bytes":8388608'
            assert original.count(needle) == 1
            mutant = root / "controlled-budget.annotation.html"
            mutant.write_bytes(original.replace(needle, b'"max_csv_bytes":1', 1))
            control = _check(browser, sdk, mutant, first["label"], None)
        finally:
            browser.close()
    assert not any(name == "quantfit" or name.startswith("quantfit.") for name in sys.modules)
    return {
        "playwright": importlib.metadata.version("playwright"),
        "chromium": version,
        "actual_browser_pages": len(results),
        "rows": sum(value["n_rows"] for value in results),
        "pages": results,
        "controlled_js_byte_limit": control,
        "pages_contexts_browser_driver_closed": True,
        "private_screenshots_traces_videos_uploads": False,
        "human_review_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().handoff)))


if __name__ == "__main__":
    main()
