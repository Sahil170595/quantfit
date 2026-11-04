"""Hosted-only SDK controller. No application imports or private artifact upload."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.metadata
import io
import json
import sys
from pathlib import Path
from typing import Any


def _choices(rows: list[list[str]]) -> list[list[str]]:
    result = []
    for index, row in enumerate(rows):
        a, b = ("refusal", "compliance") if row[1] == "refusal-robustness" else ("compliance", "refusal")
        result.append(
            ([a, b, "substantive"], [a, b, "degenerate"], [b, b, "not-a-flip"], ["unusable", b, "unresolved"])[
                index % 4
            ]
        )
    return result


def _check_page(browser: Any, sdk: Any, path: Path, rows: list[list[str]], destination: Path | None) -> dict[str, Any]:
    context = browser.new_context(accept_downloads=True, service_workers="block")
    http_requests: list[bool] = []
    console_errors: list[bool] = []
    page = None
    try:
        context.on(
            "request",
            lambda request: http_requests.append(True) if request.url.startswith(("http:", "https:")) else None,
        )
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(True) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(True))
        page.goto(path.resolve().as_uri(), wait_until="load")
        assert page.locator("article").count() == len(rows)
        assert page.locator("select").count() == 3 * len(rows)
        captions = ("Pair index", "Axis", "Zone", "Expected outcome", "Baseline completion", "Quantized completion")
        for index, original in enumerate(rows):
            article = page.locator(f'article[data-row="{index}"]')
            for column, caption in enumerate(captions):
                protected = article.locator(f'pre[data-protected="{column}"]')
                association = protected.get_attribute("aria-labelledby")
                assert association == f"field-{index}-{column}"
                assert article.locator(f"#{association}").inner_text() == caption
                assert protected.text_content() == original[column]

        assert all(
            value == ""
            for value in page.locator("select").evaluate_all("elements => elements.map(element => element.value)")
        )

        def refused() -> None:
            try:
                with page.expect_download(timeout=250):
                    page.evaluate("document.getElementById('export').dispatchEvent(new MouseEvent('click'))")
            except sdk.TimeoutError:
                pass
            else:
                raise AssertionError("Unexpected private download")
            assert "refused" in page.locator("#status").inner_text().lower()

        if rows:
            assert page.locator("#export").is_disabled()
            refused()
        page.evaluate(
            "document.querySelectorAll('article pre').forEach(element => element.textContent='DOM_CHANGED'); document.getElementById('review-data').textContent='{}'"
        )
        choices = _choices(rows)
        for index, triple in enumerate(choices):
            for column, value in enumerate(triple):
                page.locator(f"#choice-{index}-{column}").select_option(value)
        assert page.locator("#export").is_enabled()
        if rows:
            page.locator("#choice-0-0").select_option("unusable")
            assert page.locator("#export").is_disabled()
            refused()
            page.locator("#choice-0-0").select_option(choices[0][0])
        result: dict[str, Any]
        if destination is None:
            refused()
            result = {"controlled_js_byte_limit_refused": True, "selected": len(rows)}
        else:
            with page.expect_download() as pending:
                page.locator("#export").click()
            download = pending.value
            assert download.suggested_filename == "filled.adjudication.csv"
            download.save_as(str(destination))  # Complete BEFORE page/context closure.
            raw = destination.read_bytes()
            decoded = list(csv.reader(io.StringIO(raw.decode("utf8"), newline=""), strict=True))
            assert len(decoded) == len(rows) + 1 and [row[:6] for row in decoded[1:]] == [row[:6] for row in rows]
            assert [row[6:] for row in decoded[1:]] == choices
            stream = io.StringIO(newline="")
            csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
                [decoded[0], *[[*row[:6], *triple] for row, triple in zip(rows, choices, strict=True)]]
            )
            assert raw == stream.getvalue().encode() and len(raw) <= 16 * 1024 * 1024
            result = {
                "selected": len(rows),
                "six_fields_exact_after_dom_tamper": True,
                "csv_exact_utf8_quote_all_crlf": True,
                "download_saved_before_close": True,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        assert not http_requests and not console_errors
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
    manifest = json.loads((root / "handoff.json").read_bytes())
    results = []
    with sdk.sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        try:
            version = browser.version
            for case in manifest["cases"]:
                paths = {key: root / value for key, value in case["paths"].items()}
                raw = paths["queue"].read_bytes()
                rows = list(csv.reader(io.StringIO(raw.decode("utf8"), newline=""), strict=True))[1:]
                result = _check_page(browser, sdk, paths["page"], rows, paths["filled"])
                result["case"] = case["name"]
                results.append(result)
            first = manifest["cases"][0]
            paths = {key: root / value for key, value in first["paths"].items()}
            original = paths["page"].read_bytes()
            needle = b'"max_csv_bytes":16777216'
            assert original.count(needle) == 1
            mutant = root / "controlled-budget.adjudication.html"
            mutant.write_bytes(original.replace(needle, b'"max_csv_bytes":1', 1))
            rows = list(csv.reader(io.StringIO(paths["queue"].read_bytes().decode(), newline=""), strict=True))[1:]
            control = _check_page(browser, sdk, mutant, rows, None)
        finally:
            browser.close()
    assert not any(name == "quantfit" or name.startswith("quantfit.") for name in sys.modules)
    return {
        "playwright": importlib.metadata.version("playwright"),
        "chromium": version,
        "actual_browser_pages": len(results),
        "cases": results,
        "controlled_postrender_limit_mutant": control,
        "pages_contexts_browser_driver_closed": True,
        "private_screenshots_traces_videos_uploads": False,
        "human_review_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.handoff)))


if __name__ == "__main__":
    main()
