"""Private offline review transport; source-authoritative apply remains unchanged."""

from __future__ import annotations

import csv
import itertools
import json
import re
from typing import Any

from quantfit import __version__, resolution
from quantfit.adjudication_record import (
    AXES,
    CLASSES,
    LABELS,
    MAX_QUEUE_BYTES,
    PRODUCER_CHECKS,
    PROOF_LIMITS,
    SCOPE,
    _decision,
    _require,
    _version,
)
from quantfit.safety.adjudication import COLUMNS, _review_rows
from quantfit.safety.calibration_inputs import EXPECTED, MAX_CAPTURE_BYTES, ZONES
from quantfit.safety.retained_labels import MAX_RECEIPT_BYTES, _binding, _encode, _json
from quantfit.safety.retention_io import admit_outputs, hold, publish

MAX_PAGE_BYTES = 32 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")
_PREPARATION_KEYS = {
    "adjudication_preparation_schema",
    "quantfit_version",
    "inputs",
    "review_queue",
    "n_probes",
    "n_selected",
    "original_flagged_counts",
    "binding_fingerprint",
    "producer_checks",
    "proof_limits",
    "scope",
}
PAGE_SCOPE = "Supplied blank queue/preparation consistency only. Producer checks are declarations, not fresh report/capture verification. Private export carries explicit unauthenticated operator choices; unchanged native apply and model-card receivers remain authoritative. No human authentication, source authenticity, sensitivity or scientific GO."


class AdjudicationReviewError(RuntimeError):
    """Categorical refusal without private data or paths."""


def _preparation_structure(raw: bytes, queue: bytes) -> dict[str, Any]:
    value = _json(raw)
    _require(set(value) == _PREPARATION_KEYS)
    _require(type(value["adjudication_preparation_schema"]) is int and value["adjudication_preparation_schema"] == 1)
    _version(value["quantfit_version"])
    n, selected = value["n_probes"], value["n_selected"]
    _require(type(n) is int and 1 <= n <= resolution.MAX_PROBES)
    _require(type(selected) is int and 0 <= selected <= n)
    _require(type(value["inputs"]) is dict and set(value["inputs"]) == {"report", "capture"})
    for role, limit in (
        ("report", resolution.MAX_REPORT_BYTES),
        ("capture", MAX_CAPTURE_BYTES),
        ("review_queue", MAX_QUEUE_BYTES),
    ):
        item = value["review_queue"] if role == "review_queue" else value["inputs"][role]
        _require(type(item) is dict and set(item) == {"sha256", "size_bytes"})
        _require(type(item["size_bytes"]) is int and 0 < item["size_bytes"] <= limit)
        _require(type(item["sha256"]) is str and bool(_SHA.fullmatch(item["sha256"])))
    _require(value["review_queue"] == _binding(queue))
    _require(type(value["binding_fingerprint"]) is str and bool(_SHA.fullmatch(value["binding_fingerprint"])))
    counts = value["original_flagged_counts"]
    _require(type(counts) is dict and set(counts) == set(AXES))
    _require(all(type(counts[axis]) is int and 0 <= counts[axis] <= n for axis in AXES))
    _require(sum(counts.values()) == selected)
    for key, expected in (("producer_checks", PRODUCER_CHECKS), ("proof_limits", PROOF_LIMITS)):
        item = value[key]
        _require(type(item) is dict and set(item) == set(expected))
        _require(all(type(item[k]) is bool and item[k] == expected[k] for k in expected))
    _require(type(value["scope"]) is str and value["scope"] == SCOPE)
    return value


def _blank_rows(data: bytes, preparation: dict[str, Any]) -> list[list[str]]:
    rows = _review_rows(data)
    _require(len(rows) == preparation["n_selected"])
    seen: set[int] = set()
    counts = dict.fromkeys(AXES, 0)
    protected = []
    for row in rows:
        pair = int(row[0])
        _require(0 <= pair < preparation["n_probes"] and pair not in seen)
        seen.add(pair)
        _require(row[1] in AXES and row[2] in ZONES and row[3] in EXPECTED)
        _require(row[3] == ("unsafe" if row[1] == AXES[0] else "safe"))
        _require(row[6:] == ["", "", ""])
        counts[row[1]] += 1
        protected.append(row[:6])
    _require(counts == preparation["original_flagged_counts"])
    return protected


def _triplets() -> dict[str, list[list[str]]]:
    result: dict[str, list[list[str]]] = {}
    for axis in AXES:
        result[axis] = []
        for a, b, classification in itertools.product(LABELS, LABELS, CLASSES):
            try:
                _decision(axis, a, b, classification)
            except RuntimeError:
                continue
            result[axis].append([a, b, classification])
    return result


def _quoted_size(value: str) -> int:
    return 2 + len(value.encode("utf8")) + value.count('"')


def _worst_csv(rows: list[list[str]], legal: dict[str, list[list[str]]]) -> int:
    total = sum(_quoted_size(value) for value in COLUMNS) + 8 + 2
    for row in rows:
        total += (
            sum(_quoted_size(value) for value in row)
            + max(sum(_quoted_size(v) for v in choice) for choice in legal[row[1]])
            + 8
            + 2
        )
    return total


_PREFIX = b"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'"><title>Private adjudication review</title><style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:1rem}article{border:1px solid #888;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:1rem}label{display:block;margin:.6rem 0}select,button{font:inherit;padding:.4rem}#status{font-weight:bold}</style><h1>Private adjudication review</h1><p>This file contains private source strings. No automatic judgments, source authentication or scientific GO. Export is an unauthenticated declaration; use unchanged native apply with the actual report and capture.</p><p id="population"></p><div id="rows"></div><button id="export" disabled>Export filled private CSV</button><p id="status" role="status"></p><script type="application/json" id="review-data">"""
_SCRIPT = r"""</script><script>
"use strict";
(() => {
  const data = JSON.parse(document.getElementById("review-data").textContent);
  const originals = Object.freeze(data.rows.map(row => Object.freeze(row.slice())));
  const legal = Object.freeze(Object.fromEntries(Object.entries(data.legal).map(([axis, triples]) => [axis, Object.freeze(triples.map(row => Object.freeze(row.slice())))])));
  const columns = Object.freeze(data.columns.slice());
  const states = originals.map(() => ["", "", ""]);
  const urls = [];
  const maxCsvBytes = data.max_csv_bytes;
  const button = document.getElementById("export");
  const status = document.getElementById("status");
  const valid = (row, choices) => legal[row[1]].some(triple => triple.every((value, index) => value === choices[index]));
  const complete = () => originals.every((row, index) => valid(row, states[index]));
  const refresh = () => {button.disabled = !complete(); status.textContent = complete() ? "Ready for explicit private export." : "Choose both labels and a valid native class for every row.";};
  document.getElementById("population").textContent = "Original probes: " + data.n_probes + "; selected rows: " + originals.length;
  originals.forEach((row, index) => {
    const article = document.createElement("article"); article.dataset.row = String(index);
    const heading = document.createElement("h2"); heading.textContent = "Selected row " + (index + 1); article.append(heading);
    row.forEach((value, column) => {
      const caption = document.createElement("h3"); caption.id = "field-" + index + "-" + column;
      caption.textContent = ["Pair index", "Axis", "Zone", "Expected outcome", "Baseline completion", "Quantized completion"][column];
      const text = document.createElement("pre"); text.dataset.protected = String(column); text.textContent = value;
      text.setAttribute("aria-labelledby", caption.id); article.append(caption, text);
    });
    [data.labels, data.labels, data.classes].forEach((choices, column) => {
      const label = document.createElement("label"); label.textContent = ["Baseline label", "Quantized label", "Flip class"][column];
      const select = document.createElement("select"); select.id = "choice-" + index + "-" + column;
      const empty = document.createElement("option"); empty.value = ""; empty.textContent = "Choose explicitly"; select.append(empty);
      choices.forEach(value => {const option = document.createElement("option"); option.value = value; option.textContent = value; select.append(option);});
      select.addEventListener("change", () => {states[index][column] = select.value; refresh();}); label.append(select); article.append(label);
    });
    document.getElementById("rows").append(article);
  });
  const quoted = value => '"' + value.replaceAll('"', '""') + '"';
  button.addEventListener("click", () => {
    if (!complete()) {status.textContent = "Export refused: incomplete or invalid choices."; return;}
    const rows = [columns, ...originals.map((row, index) => [...row, ...states[index]])];
    const csv = rows.map(row => row.map(quoted).join(",") + "\r\n").join("");
    const bytes = new TextEncoder().encode(csv);
    if (bytes.byteLength > maxCsvBytes) {status.textContent = "Export refused: encoded CSV exceeds the native byte limit."; return;}
    const url = URL.createObjectURL(new Blob([bytes], {type: "text/csv;charset=utf-8"})); urls.push(url);
    const link = document.createElement("a"); link.href = url; link.download = "filled.adjudication.csv"; document.body.append(link); link.click(); link.remove();
    status.textContent = "Private download requested. Native apply remains required.";
  });
  window.addEventListener("pagehide", () => {urls.forEach(url => URL.revokeObjectURL(url)); urls.length = 0;});
  refresh();
})();
</script></html>""".encode("ascii")


def _page(payload: dict[str, Any]) -> bytes:
    output = bytearray(_PREFIX)
    _require(len(output) + len(_SCRIPT) <= MAX_PAGE_BYTES)
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    for chunk in encoder.iterencode(payload):
        raw = chunk.replace("<", "\\u003c").encode("ascii")
        _require(len(output) + len(raw) + len(_SCRIPT) <= MAX_PAGE_BYTES)
        output.extend(raw)
    output.extend(_SCRIPT)
    return bytes(output)


def _receive(review: str, preparation: str, *, out_path: str) -> tuple[dict[str, Any], bytes]:
    try:
        _require(all(type(value) is str and bool(value) for value in (review, preparation, out_path)))
        _require(out_path.endswith(".adjudication.html"))
        inputs = (hold(review, MAX_QUEUE_BYTES), hold(preparation, MAX_RECEIPT_BYTES))
        target = admit_outputs((out_path,), inputs)[0]
        metadata = _preparation_structure(inputs[1].data, inputs[0].data)
        rows = _blank_rows(inputs[0].data, metadata)
        legal = _triplets()
        worst = _worst_csv(rows, legal)
        _require(worst <= MAX_QUEUE_BYTES)
        html = _page(
            {
                "rows": rows,
                "legal": legal,
                "columns": COLUMNS,
                "labels": LABELS,
                "classes": CLASSES,
                "n_probes": metadata["n_probes"],
                "max_csv_bytes": MAX_QUEUE_BYTES,
            }
        )
        receipt = {
            "adjudication_review_page_schema": 1,
            "quantfit_version": __version__,
            "inputs": {"review_queue": _binding(inputs[0].data), "preparation": _binding(inputs[1].data)},
            "page": _binding(html),
            "n_probes": metadata["n_probes"],
            "n_selected": len(rows),
            "worst_filled_csv_bytes": worst,
            "max_csv_bytes": MAX_QUEUE_BYTES,
            "max_html_bytes": MAX_PAGE_BYTES,
            "preparation_consistent": True,
            "source_verified": False,
            "human_confirmation_verified": False,
            "scientific_go": False,
            "scope": PAGE_SCOPE,
        }
        from quantfit.cli import _json_document

        encoded = (
            json.dumps(_json_document("adjudicate review-page", 0, receipt), indent=2, allow_nan=False) + "\n"
        ).encode()
        _require(len(_encode(receipt)) <= MAX_RECEIPT_BYTES and len(encoded) <= MAX_RECEIPT_BYTES)
        publish(((target, html),), inputs)
        return receipt, encoded
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        ImportError,
        csv.Error,
    ):
        raise AdjudicationReviewError("invalid_adjudication_review") from None


def render_adjudication_review(review: str, preparation: str, *, out_path: str) -> dict[str, Any]:
    """Create one private page; only supplied preparation consistency is established."""
    return _receive(review, preparation, out_path=out_path)[0]
