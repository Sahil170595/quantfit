"""Private blinded full-population pages; native collection remains authoritative."""

from __future__ import annotations

import csv
import json
from typing import Any

from quantfit import __version__
from quantfit.safety import annotation_chunks as chunks
from quantfit.safety import calibrate
from quantfit.safety.label_review import _csv
from quantfit.safety.reconcile import MAX_KEY_BYTES, MAX_SHEET_BYTES
from quantfit.safety.retained_labels import MAX_RECEIPT_BYTES, _binding, _encode, _json
from quantfit.safety.retention_io import HeldFile, admit_outputs, canonical, publish, require

MAX_PAGE_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
SCOPE = (
    "Private page transport of every assigned native blinded row only. Original blank/key/manifest consistency "
    "is checked; no capture is read or source/rater/human authenticity established. Full local production grants "
    "no sharing permission. Existing native complete collection and separate ingestion remain required. "
    "No automatic labeling, sending, independence, sensitivity, spreadsheet-formula safety or scientific GO. "
    "Native exclusive per-file publication is not a directory transaction or hostile-filesystem/heap guarantee."
)


class AnnotationPacketsError(RuntimeError):
    """Categorical refusal without private strings or caller paths."""


def _quoted_size(value: str) -> int:
    return 2 + len(value.encode("utf-8")) + value.count('"')


def _worst_part(rows: list[dict[str, Any]], label: str) -> int:
    return (
        sum(_quoted_size(v) for v in calibrate.SHEET_COLUMNS)
        + 4
        + sum(_quoted_size(row["id"]) + _quoted_size(row["completion"]) + _quoted_size(label) + 4 for row in rows)
    )


def _roundtrip_bounds(
    inputs: tuple[HeldFile, ...],
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    assigned: list[list[dict[str, Any]]],
) -> tuple[list[int], dict[str, int]]:
    label = max(calibrate.HUMAN_LABELS, key=_quoted_size)
    worst = [_worst_part(part, label) for part in assigned]
    require(all(size <= MAX_SHEET_BYTES for size in worst))
    remaining = chunks.MAX_INPUT_BYTES - sum(len(item.data) for item in inputs)
    require(sum(worst) <= remaining)
    # Native minimal quoting and its native 8MiB cap are also the later extraction domain.
    full = _csv([(row["id"], row["completion"], label) for row in rows])
    bound_receipt = {
        **chunks._summary(manifest, inputs[2].data),
        "parts": [
            {
                "index": part["index"],
                "n_rows": len(part["ids"]),
                "blank_sheet": part["blank_sheet"],
                "filled_sheet": {"sha256": "0" * 64, "size_bytes": size},
            }
            for part, size in zip(manifest["parts"], worst, strict=True)
        ],
        "output_sheet": _binding(full),
        "n_unusable": manifest["n_rows"],
    }
    receipt_bytes = len(_encode(bound_receipt))
    require(receipt_bytes <= MAX_RECEIPT_BYTES and len(full) + receipt_bytes <= chunks.MAX_OUTPUT_BYTES)
    return worst, {
        "remaining_collector_input_bytes": remaining,
        "worst_all_filled_parts_bytes": sum(worst),
        "worst_reconstructed_sheet_bytes": len(full),
        "worst_collection_receipt_bytes": receipt_bytes,
        "native_collection_output_limit_bytes": chunks.MAX_OUTPUT_BYTES,
    }


_PREFIX = b"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'"><title>Private blinded annotation</title><style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:1rem}article{border:1px solid #888;padding:1rem;margin:1rem 0}pre,code{white-space:pre-wrap;overflow-wrap:anywhere}pre{background:#eee;padding:1rem}label{display:block;margin:.6rem 0}select,button{font:inherit;padding:.4rem}#status{font-weight:bold}</style><h1>Private blinded annotation</h1><p>Private completion text. Choose every label explicitly. Export requires native collection and separate ingestion. No authenticated human judgment or scientific claim. No network requests.</p><div id="rows"></div><button id="export" disabled>Export filled private CSV</button><p id="status" role="status"></p><script type="application/json" id="annotation-data">"""
_SCRIPT = r"""</script><script>
"use strict";
(() => {
 const data = JSON.parse(document.getElementById("annotation-data").textContent);
 const originals = Object.freeze(data.rows.map(row => Object.freeze(row.slice())));
 const labels = Object.freeze(["refusal", "compliance", "unusable"]);
 const columns = Object.freeze(["id", "completion", "human_label"]);
 const states = originals.map(() => "");
 const filename = data.filename;
 const maxCsvBytes = data.max_csv_bytes;
 const button = document.getElementById("export");
 const status = document.getElementById("status");
 let url = null;
 const complete = () => originals.length > 0 && states.every(value => labels.includes(value));
 const refresh = () => {button.disabled = !complete(); status.textContent = complete() ? "Ready for explicit private export." : "Choose a label for every completion.";};
 originals.forEach((row, index) => {
  const article = document.createElement("article"); article.dataset.row = String(index);
  const heading = document.createElement("h2"); heading.textContent = "Completion " + (index + 1); article.append(heading);
  const ident = document.createElement("code"); ident.dataset.protected = "0"; ident.textContent = row[0]; article.append(ident);
  const text = document.createElement("pre"); text.dataset.protected = "1"; text.textContent = row[1]; article.append(text);
  const label = document.createElement("label"); label.textContent = "Explicit label";
  const select = document.createElement("select"); select.id = "choice-" + index;
  const empty = document.createElement("option"); empty.value = ""; empty.textContent = "Choose explicitly"; select.append(empty);
  labels.forEach(value => {const option = document.createElement("option"); option.value = value; option.textContent = value; select.append(option);});
  select.addEventListener("change", () => {states[index] = select.value; refresh();}); label.append(select); article.append(label);
  document.getElementById("rows").append(article);
 });
 const quoted = value => '"' + value.replaceAll('"', '""') + '"';
 button.addEventListener("click", () => {
  if (!complete()) {status.textContent = "Export refused: incomplete or invalid choices."; return;}
  const csv = [columns, ...originals.map((row,index) => [...row, states[index]])].map(row => row.map(quoted).join(",") + "\r\n").join("");
  const bytes = new TextEncoder().encode(csv);
  if (bytes.byteLength > maxCsvBytes) {status.textContent = "Export refused: encoded CSV exceeds the native byte limit."; return;}
  if (url !== null) URL.revokeObjectURL(url);
  url = URL.createObjectURL(new Blob([bytes], {type:"text/csv;charset=utf-8"}));
  const link = document.createElement("a"); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
  status.textContent = "Private download requested. Native collection remains required.";
 });
 window.addEventListener("pagehide", () => {if (url !== null) URL.revokeObjectURL(url); url = null;});
 refresh();
})();
</script></html>""".encode("ascii")


def _page(payload: dict[str, Any]) -> bytes:
    output = bytearray(_PREFIX)
    require(len(output) + len(_SCRIPT) <= MAX_PAGE_BYTES)
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    for chunk in encoder.iterencode(payload):
        raw = chunk.replace("<", "\\u003c").encode("ascii")
        require(len(output) + len(raw) + len(_SCRIPT) <= MAX_PAGE_BYTES)
        output.extend(raw)
    output.extend(_SCRIPT)
    return bytes(output)


def prepare_annotation_packets(sheet_path: str, key_path: str, manifest_path: str, *, out_dir: str) -> dict[str, Any]:
    """Publish one fresh private page per native part, never its unblinding inputs."""
    try:
        directory = canonical(out_dir)
        require(directory.is_dir() and not any(directory.iterdir()))
        inputs = chunks._held(
            (sheet_path, key_path, manifest_path),
            (MAX_SHEET_BYTES, MAX_KEY_BYTES, chunks.MAX_MANIFEST_BYTES),
        )
        manifest = _json(inputs[2].data)
        version = manifest["quantfit_version"]
        require(type(version) is str and 0 < len(version) <= 64)
        declared = manifest["annotator_declared"]
        require(type(declared) is dict and set(declared) == {"role", "name"})
        expected, _, rows = chunks._preparation(
            inputs, manifest["rows_per_part"], chunks._annotator(declared["role"], declared["name"]), version
        )
        require(_encode(expected) == _encode(manifest))
        by_id = {row["id"]: row for row in rows}
        assigned = [[by_id[ident] for ident in part["ids"]] for part in manifest["parts"]]
        worst, bounds = _roundtrip_bounds(inputs, manifest, rows, assigned)
        pages: list[bytes] = []
        part_receipts = []
        total = 0
        for part, subset, size in zip(manifest["parts"], assigned, worst, strict=True):
            html = _page(
                {
                    "annotation_packet_schema": 1,
                    "rows": [[row["id"], row["completion"]] for row in subset],
                    "filename": part["filename"],
                    "max_csv_bytes": MAX_SHEET_BYTES,
                }
            )
            total += len(html)
            require(total <= MAX_OUTPUT_BYTES)
            pages.append(html)
            part_receipts.append(
                {
                    "index": part["index"],
                    "n_rows": len(subset),
                    "blank_sheet": part["blank_sheet"],
                    "page": _binding(html),
                    "worst_filled_csv_bytes": size,
                }
            )
        receipt = {
            "annotation_packets_schema": 1,
            "quantfit_version": __version__,
            "inputs": {
                role: _binding(item.data) for role, item in zip(("sheet", "key", "manifest"), inputs, strict=True)
            },
            "n_pairs": manifest["n_pairs"],
            "n_rows": manifest["n_rows"],
            "n_parts": manifest["n_parts"],
            "parts": part_receipts,
            "native_roundtrip_bounds": bounds,
            "max_page_bytes": MAX_PAGE_BYTES,
            "max_all_output_bytes": MAX_OUTPUT_BYTES,
            "limits": dict(chunks.LIMITS),
            "scope": SCOPE,
        }
        require(len(_encode(receipt)) <= MAX_RECEIPT_BYTES and total + len(_encode(receipt)) <= MAX_OUTPUT_BYTES)
        from quantfit.cli import _json_document

        encoded = (
            json.dumps(_json_document("calibrate chunks packets", 0, receipt), indent=2, allow_nan=False) + chr(10)
        ).encode()
        require(len(encoded) <= MAX_RECEIPT_BYTES and total + len(encoded) <= MAX_OUTPUT_BYTES)
        paths = tuple(str(directory / f"part-{part['index']:04d}.annotation.html") for part in manifest["parts"])
        targets = admit_outputs(paths, inputs)
        publish(tuple(zip(targets, pages, strict=True)), inputs)
        return receipt
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
        raise AnnotationPacketsError("invalid_annotation_packets") from None
