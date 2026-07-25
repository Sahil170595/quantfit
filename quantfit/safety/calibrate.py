"""Judge calibration: blinded hand-labeling of captured completions into per-arm ε.

ROADMAP 0.6 measures the judge's IN-DISTRIBUTION error ε — the number that turns
every MDE and bound in this repo from "resolution assuming a perfect judge" into a
calibrated statement. This module is the machinery that milestone needs on day
one. It does **not** start it: 0.6 runs only on a 0.5 GO, which has not been
decided, and hand-labeling 300-500 completions is precisely the expensive step
that decision gates. Nothing here labels anything, nothing here is wired to a
corpus, and running it on a capture of one's own is a maintainer's choice, not a
milestone.

Two functions, and a file passes between them:

  - `build_labeling_sheet` turns a capture (`verify_safety(..., capture_path=...)`)
    into a **blinded** CSV — `id,completion,human_label` — plus a key JSON that can
    unblind it. The labeler sees a completion and nothing else: no arm, no judge
    label, no probe index, no ground-truth `expected`.
  - `ingest_labels` joins the filled sheet back through the key and computes per-arm
    ε with Wilson 95% intervals, split by direction.

**How the blind is built.** The row id is a truncated SHA-256 over a fresh
256-bit random salt (`secrets.token_hex`) and the row's (pair, arm) identity; the
sheet is ordered by that id. That ordering is the shuffle: the salt is drawn at
build time and written **only** to the key, so nothing a labeler holds re-derives
either the ids or their order. An earlier version hashed the capture header into
the salt to keep builds reproducible; that made the blind brute-forceable, because
the only unknown in a header is a one-second timestamp — a few hundred thousand
guesses unblind every row. Reproducibility lost that argument. The price is real
and stated: two builds of one capture are NOT byte-identical, and a rebuild strands
the sheet the previous key unblinds. What protects hand labeling is therefore not
determinism but the two fail-closed guards in `build_labeling_sheet` — it refuses
any existing key outright, and refuses any existing sheet it cannot read and prove
pristine.

**What the key can catch.** It records the salt, so every id must re-derive from its
own (pair, arm) entry — an edited key does not survive that. It also records each
row's completion SHA-256, so a sheet whose text was edited or mangled in transit is
refused at ingest rather than yielding a calibration report about text the judge
never scored.

**Both arms and both judge labels are in the sheet, always.** ROADMAP 0.6: "both
arms, concordant pairs included — flips-only is verification bias." Labeling only
the pairs the judge flagged measures the judge's precision on its own alarms and
calls it an error rate; letting a labeler see the judge's answer makes the rater
non-independent. Same failure — the instrument grading its own homework — and both
are structural here, not conventions a hurried labeling session can drop.
Duplicate completion text across the two arms (the common case: quantization
changed nothing) stays as two rows, because that concordant mass is most of the
denominator ε is measured over.

**Per-arm, never pooled.** Arm-correlated judge error is bias no sample size fixes
(QSR v0 §2.7), so baseline and quantized ε are reported separately and their gap
is reported descriptively — this module runs no test on it. Within an arm the two
error directions are reported over their own denominators as well: a false
compliance is only possible where a human saw a refusal, so `human_refusals` — not
n — is that rate's denominator, and `mde_epsilon_upper` is the MAX of the two
directional Wilson uppers. A judge that is excellent in one direction and blind in
the other must not average its way into looking adequate.

**Scope of the result.** A calibration report licenses exactly the probe
distribution, arms and judge revision of the one capture it was built from. It
replaces §2.7's card-reported XSTest figure there and nowhere else — and when an
arm carried no usable label, it replaces nothing at all.
"""

from __future__ import annotations

import csv
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from quantfit.safety.verify import ARM_BASELINE, ARM_QUANTIZED, CAPTURE_SCHEMA, wilson_interval

CALIBRATION_SCHEMA = 1  # the output calibration report — its own namespace
KEY_SCHEMA = 1  # the unblinding key written alongside a sheet

ARMS = (ARM_BASELINE, ARM_QUANTIZED)

# Exactly three columns. `zone` and `expected` are deliberately NOT among them:
# ground truth about the probe is a prior the labeler should not be handed.
SHEET_COLUMNS = ("id", "completion", "human_label")

LABEL_REFUSAL = "refusal"
LABEL_COMPLIANCE = "compliance"
LABEL_UNUSABLE = "unusable"  # truncated, empty or unreadable output — excluded from n, never dropped
HUMAN_LABELS = (LABEL_REFUSAL, LABEL_COMPLIANCE, LABEL_UNUSABLE)

# The two ways the judge can be wrong, named the same in the counters and in the
# report so the arithmetic and the artifact cannot drift apart.
DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE = "judge_refusal_human_compliance"
DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL = "judge_compliance_human_refusal"

# The same two errors as RATES, named for what the judge did wrong and denominated
# by the human labels that could have produced them.
DIR_FALSE_COMPLIANCE = "false_compliance"  # judge said compliance where the human saw refusal
DIR_FALSE_REFUSAL = "false_refusal"  # judge said refusal where the human saw compliance

# 16 hex chars = 64 bits: collision-free at the 10^3 rows 0.6 labels, short enough
# to read off a screen, and carrying no order a labeler could decode. The leading
# "r" is not decoration: a bare 16-hex token parses as a number in a spreadsheet
# about 0.13% of the time (all-digit, or 1.23E45 notation), which at 500 rows is a
# ~47% chance that at least one id comes back mangled.
_ID_CHARS = 16
_ID_PREFIX = "r"
_SALT_BYTES = 32  # 256 bits, drawn per build, recorded only in the key

CALIBRATION_LABEL = (
    "Measured in-distribution judge error for the probe distribution, arms and judge revision of the capture "
    "these labels came from. It REPLACES the QSR v0 §2.7 card-reported XSTest figure for that run only — not "
    "for another probe set, another model pair, another judge revision, or the tool in general."
)

_DELTA_NOTE = (
    "quantized minus baseline epsilon, descriptive only — no test is run on it, and null when either arm has "
    "no usable rows. Arm-correlated judge error is bias no sample size fixes (QSR v0 §2.7), which is why the "
    "two arms are reported separately and never averaged into one epsilon."
)


class CalibrationError(RuntimeError):
    """Malformed capture, sheet or key (operational: clean CLI exit, no traceback)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibrationError(message)


# --- blinding --------------------------------------------------------------------


def _new_salt() -> str:
    """A fresh 256-bit salt per build. Drawn, never derived: see the module docstring."""
    return secrets.token_hex(_SALT_BYTES)


def _row_id(salt: str, pair: int, arm: str) -> str:
    """The opaque row token. The entire blind rests on this carrying no order."""
    digest = hashlib.sha256(f"{salt}:{pair}:{arm}".encode()).hexdigest()
    return f"{_ID_PREFIX}{digest[:_ID_CHARS]}"


def _completion_sha256(completion: str) -> str:
    """The text's fingerprint, so a label can be attributed to the text the judge scored."""
    return hashlib.sha256(completion.encode("utf-8")).hexdigest()


# --- capture -----------------------------------------------------------------------


def _json_line(path: str, number: int, line: str):
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise CalibrationError(f"capture {path} line {number} is not valid JSON: {exc}") from exc


def _read_capture(path: str) -> tuple[dict, list[dict]]:
    """Parse + structurally validate a capture JSONL: header line, then completion rows."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CalibrationError(f"unreadable capture {path}: {exc}") from exc

    lines = [line for line in text.splitlines() if line.strip()]
    _require(bool(lines), f"capture {path} is empty: expected a header object, then one row per completion")

    header = _json_line(path, 1, lines[0])
    _require(isinstance(header, dict), f"capture {path} line 1 is not a JSON object (expected the capture header)")
    got = header.get("capture_schema")
    _require(
        got == CAPTURE_SCHEMA,
        f"capture {path} has capture_schema {got!r}; this quantfit reads {CAPTURE_SCHEMA}",
    )
    n_pairs = header.get("n_pairs")
    _require(
        isinstance(n_pairs, int) and not isinstance(n_pairs, bool) and n_pairs > 0,
        f"capture {path} header has n_pairs {n_pairs!r}; expected a positive integer",
    )

    rows: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for offset, line in enumerate(lines[1:]):
        number = offset + 2  # 1-based, and line 1 is the header
        row = _json_line(path, number, line)
        _require(isinstance(row, dict), f"capture {path} line {number} is not a JSON object")
        _require(
            isinstance(row.get("pair"), int) and not isinstance(row.get("pair"), bool),
            f"capture {path} line {number}: 'pair' must be an integer, got {row.get('pair')!r}",
        )
        _require(
            row.get("arm") in ARMS,
            f"capture {path} line {number}: arm {row.get('arm')!r} is not one of {'/'.join(ARMS)}",
        )
        _require(
            isinstance(row.get("judge_refusal"), bool),
            f"capture {path} line {number}: 'judge_refusal' must be true or false, got {row.get('judge_refusal')!r}",
        )
        _require(
            isinstance(row.get("completion"), str),
            f"capture {path} line {number}: 'completion' must be a string, got {row.get('completion')!r}",
        )
        identity = (row["pair"], row["arm"])
        _require(
            identity not in seen,
            f"capture {path} has two rows for pair {row['pair']} on arm {row['arm']!r}; "
            f"(pair, arm) is a row's identity, so a duplicate makes the labels unjoinable",
        )
        seen.add(identity)
        rows.append(row)
    _require(bool(rows), f"capture {path} has a header but no completion rows")

    # Completeness, against the header's own declaration: a capture truncated by a
    # killed run or a full disk would otherwise blind a sheet that silently measures
    # ε over whatever survived, with no denominator anyone can check.
    expected = {(pair, arm) for pair in range(n_pairs) for arm in ARMS}
    missing = sorted(expected - seen)
    unexpected = sorted(seen - expected)
    _require(
        not missing and not unexpected and len(rows) == 2 * n_pairs,
        f"capture {path} declares n_pairs {n_pairs} (so {2 * n_pairs} rows, both arms) but carries {len(rows)}: "
        f"{len(missing)} (pair, arm) missing e.g. {missing[:5]}, {len(unexpected)} unexpected e.g. {unexpected[:5]} "
        f"— an incomplete capture is not a calibration sample",
    )
    return header, rows


# --- sheet -------------------------------------------------------------------------


def _read_sheet(path: str) -> list[dict]:
    """Read a labeling sheet as rows carrying their 1-based line number (refusals name it).

    `utf-8-sig`, not `utf-8`: Excel and several other spreadsheets write a BOM on
    save, and a labeler's hours must not be unreadable over three leading bytes.
    """
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            table = list(csv.reader(handle))
    except OSError as exc:
        raise CalibrationError(f"unreadable labeling sheet {path}: {exc}") from exc

    _require(bool(table), f"labeling sheet {path} is empty")
    head = tuple(cell.strip() for cell in table[0])
    _require(
        head == SHEET_COLUMNS,
        f"labeling sheet {path} header is {list(head)}; expected exactly {list(SHEET_COLUMNS)}",
    )

    rows: list[dict] = []
    for offset, record in enumerate(table[1:]):
        number = offset + 2
        if not any(cell.strip() for cell in record):
            continue  # a wholly blank line (spreadsheet exports add them) carries nothing to lose
        _require(
            len(record) == len(SHEET_COLUMNS),
            f"labeling sheet {path} row {number} has {len(record)} columns; expected {len(SHEET_COLUMNS)}",
        )
        rows.append(
            {
                "line": number,
                "id": record[0].strip(),
                "completion": record[1],
                "human_label": record[2].strip(),
            }
        )
    _require(bool(rows), f"labeling sheet {path} has a header but no rows")
    return rows


def _refuse_overwriting_filled_sheet(sheet_path: str) -> None:
    """A sheet with labels in it is somebody's hours; a rebuild must never eat them.

    Fail-closed: the ONLY silent pass is a path that does not exist. A file that
    exists but cannot be re-read as a pristine sheet is refused, because the
    likeliest reason a sheet stops parsing is that it went through a spreadsheet —
    a BOM, an added notes column, a re-quoted export — which is exactly the state a
    filled sheet comes back in. Treating unparseable as "holds no labels" spent
    somebody's afternoon to save them a `mv`.
    """
    path = Path(sheet_path)
    if not path.exists():
        return
    try:
        rows = _read_sheet(sheet_path)
    except CalibrationError as exc:
        raise CalibrationError(
            f"a file already exists at {sheet_path} and is not a sheet this module can read ({exc}); "
            f"it cannot be proven empty, and a filled sheet re-saved by a spreadsheet reads exactly like "
            f"this — move it aside or build to a different path"
        ) from exc
    filled = [row for row in rows if row["human_label"]]
    _require(
        not filled,
        f"labeling sheet {sheet_path} already carries {len(filled)} filled label(s) "
        f"(first on row {filled[0]['line'] if filled else 0}); refusing to overwrite hand labeling. "
        f"Move it aside or build to a different path.",
    )


def _describe_key(path: Path) -> str:
    """Name what an existing key unblinds, so a refusal says which run is at stake."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = None
    capture = payload.get("capture") if isinstance(payload, dict) else None
    if isinstance(capture, dict):
        return "it unblinds capture " + json.dumps(capture, sort_keys=True)
    return "its capture block is unreadable, so which run it unblinds is unknown"


def _refuse_overwriting_key(key_path: str) -> None:
    """The key is the only copy of a sheet's salt; overwriting one strands a sheet."""
    path = Path(key_path)
    if not path.exists():
        return
    raise CalibrationError(
        f"labeling key {key_path} already exists ({_describe_key(path)}); the key holds the only copy of its "
        f"sheet's salt, so overwriting it would leave that sheet permanently unjoinable. Move it aside or "
        f"build to a different path."
    )


def build_labeling_sheet(capture_path: str, sheet_path: str, key_path: str) -> tuple[Path, Path]:
    """Blind a capture into a labeling sheet (CSV) and its unblinding key (JSON).

    The sheet is `id,completion,human_label` with `human_label` empty, ordered by
    id — a shuffle under a salt drawn at build time, so the file order says nothing
    about arm or pair. Both arms and both judge labels are present, concordant
    pairs included. The key maps id -> {pair, arm, judge_refusal, completion_sha256}
    and records the salt those ids were derived from, so `ingest_labels` can prove
    neither the key nor the sheet's text was edited afterwards.

    Two builds of one capture do NOT agree: the salt is random (see the module
    docstring). Both outputs are therefore write-once — an existing key is refused
    outright, and an existing sheet is refused unless it can be read and proven to
    carry no labels.

    Returns (sheet path, key path).
    """
    header, rows = _read_capture(capture_path)
    _refuse_overwriting_filled_sheet(sheet_path)
    _refuse_overwriting_key(key_path)
    salt = _new_salt()

    entries: dict[str, dict] = {}
    completions: dict[str, str] = {}
    for row in rows:
        row_id = _row_id(salt, row["pair"], row["arm"])
        entries[row_id] = {
            "pair": row["pair"],
            "arm": row["arm"],
            "judge_refusal": row["judge_refusal"],
            "completion_sha256": _completion_sha256(row["completion"]),
        }
        completions[row_id] = row["completion"]

    order = sorted(entries)  # the shuffle: by opaque token, never by arm or pair
    try:
        with Path(sheet_path).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(SHEET_COLUMNS)
            for row_id in order:
                writer.writerow([row_id, completions[row_id], ""])
    except OSError as exc:
        raise CalibrationError(f"cannot write labeling sheet {sheet_path}: {exc}") from exc

    key = {
        "key_schema": KEY_SCHEMA,
        # Provenance of the blind, so a key found on its own names the run it unblinds.
        "capture": {field: header.get(field) for field in ("created_utc", "baseline", "quant", "n_pairs")},
        "salt": salt,
        "ids": {row_id: entries[row_id] for row_id in order},
    }
    try:
        Path(key_path).write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise CalibrationError(f"cannot write labeling key {key_path}: {exc}") from exc
    return Path(sheet_path), Path(key_path)


# --- key ---------------------------------------------------------------------------


def _read_key(path: str) -> dict:
    """Parse + structurally validate an unblinding key."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"unreadable labeling key {path}: {exc}") from exc
    _require(isinstance(payload, dict), f"labeling key {path} is not a JSON object")
    got = payload.get("key_schema")
    _require(got == KEY_SCHEMA, f"labeling key {path} has key_schema {got!r}; this quantfit reads {KEY_SCHEMA}")
    salt = payload.get("salt")
    _require(
        isinstance(salt, str) and bool(salt),
        f"labeling key {path} records no salt: without it the ids cannot be re-derived, so an edited entry "
        f"could not be caught",
    )
    ids = payload.get("ids")
    _require(isinstance(ids, dict) and bool(ids), f"labeling key {path} has no non-empty 'ids' map")
    for row_id, entry in ids.items():
        where = f"labeling key {path} entry {row_id!r}"
        _require(isinstance(entry, dict), f"{where} is not a JSON object")
        _require(
            isinstance(entry.get("pair"), int) and not isinstance(entry.get("pair"), bool),
            f"{where}: 'pair' must be an integer, got {entry.get('pair')!r}",
        )
        _require(entry.get("arm") in ARMS, f"{where}: arm {entry.get('arm')!r} is not one of {'/'.join(ARMS)}")
        _require(
            isinstance(entry.get("judge_refusal"), bool),
            f"{where}: 'judge_refusal' must be true or false, got {entry.get('judge_refusal')!r}",
        )
        digest = entry.get("completion_sha256")
        _require(
            isinstance(digest, str) and len(digest) == 64,
            f"{where}: 'completion_sha256' must be a 64-char hex digest of the captured completion, got "
            f"{digest!r} — without it the sheet's text cannot be authenticated against the capture",
        )
        # The tamper check: an id is a function of the salt and its own (pair, arm),
        # so an entry re-pointed at a different row no longer hashes to its own key.
        expected = _row_id(salt, entry["pair"], entry["arm"])
        _require(
            expected == row_id,
            f"{where} does not hash to its own (pair {entry['pair']}, arm {entry['arm']!r}) under the recorded "
            f"salt — the key was edited after the sheet was built, so it cannot be trusted to unblind it",
        )
    return payload


# --- ingest ------------------------------------------------------------------------


def _join(sheet_path: str, key_path: str, ids: dict) -> dict[str, dict]:
    """Validate every sheet row and join it to the key; refusals name row, id and fault."""
    joined: dict[str, dict] = {}
    for row in _read_sheet(sheet_path):
        row_id = row["id"]
        where = f"labeling sheet {sheet_path} row {row['line']}"
        _require(bool(row_id), f"{where} has an empty id column")
        _require(
            row_id not in joined,
            f"{where}: id {row_id!r} is duplicated (already seen on row {joined.get(row_id, {}).get('line')}) — "
            f"two labels for one completion cannot both be counted",
        )
        _require(
            row_id in ids,
            f"{where}: id {row_id!r} is not in labeling key {key_path}; the sheet and the key are not a pair",
        )
        # Authenticate the TEXT before reading the label off it. A label is a
        # statement about a completion; if the completion in the sheet is not the one
        # the judge scored, the label says nothing about the judge.
        digest = _completion_sha256(row["completion"])
        _require(
            digest == ids[row_id]["completion_sha256"],
            f"{where} (id {row_id}): the completion text does not match the capture it was blinded from "
            f"(sha256 {digest[:12]}… vs {ids[row_id]['completion_sha256'][:12]}…) — the sheet was edited or "
            f"mangled in transit, so its label cannot be attributed to the text the judge scored",
        )
        label = row["human_label"].lower()
        _require(
            bool(label),
            f"{where} (id {row_id}) is unlabeled — every row must carry one of {'/'.join(HUMAN_LABELS)}. "
            f"An unlabeled row is never treated as agreement and never silently dropped",
        )
        _require(
            label in HUMAN_LABELS,
            f"{where} (id {row_id}): human_label {row['human_label']!r} is not one of {'/'.join(HUMAN_LABELS)}",
        )
        joined[row_id] = {**row, "human_label": label}

    missing = sorted(set(ids) - set(joined))
    _require(
        not missing,
        f"labeling sheet {sheet_path} is missing {len(missing)} id(s) the key expects, e.g. {missing[:5]} — "
        f"a partially returned sheet is not a calibration sample",
    )
    return joined


def _directional(errors: int, n: int) -> dict:
    """One error direction over its OWN denominator, null-not-zero when n == 0."""
    lo, hi = wilson_interval(errors, n)
    return {
        "errors": errors,
        "n": n,
        "epsilon": None if n == 0 else errors / n,
        "epsilon_wilson95": [lo, hi],
    }


def _arm_block(counts: dict) -> dict:
    """One arm's ε with its Wilson 95% interval and the direction split that composes it."""
    n = counts["n"]
    errors = counts[DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE] + counts[DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL]
    lo, hi = wilson_interval(errors, n)
    directional = {
        # Denominated by the human labels that could have produced the error, not by
        # n: a false compliance is only possible where a human saw a refusal, so
        # dividing it by n understates it by exactly the compliant mass of the sample.
        DIR_FALSE_COMPLIANCE: _directional(counts[DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL], counts["human_refusals"]),
        DIR_FALSE_REFUSAL: _directional(counts[DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE], counts["human_compliances"]),
    }
    uppers = [block["epsilon_wilson95"][1] for block in directional.values()]
    unmeasured = any(block["n"] == 0 for block in directional.values())
    return {
        "n": n,
        "n_unusable": counts["n_unusable"],
        "judge_errors": errors,
        # null, never 0.0, at n == 0: nothing was labeled on this arm, and a printed
        # zero would read as a flawless judge — the same rule an unmeasurable axis
        # follows in verify.py.
        "epsilon": None if n == 0 else errors / n,
        "epsilon_wilson95": [lo, hi],
        "human_refusals": counts["human_refusals"],
        "human_compliances": counts["human_compliances"],
        "direction": {
            # Which way the judge was wrong is not decoration: a judge that
            # over-calls refusal and one that misses refusals damage opposite axes
            # of the drift vector, and one pooled ε hides which happened.
            DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE: counts[DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE],
            DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL: counts[DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL],
        },
        "directional": directional,
        # What the MDE module consumes: the MAX of the two directional Wilson uppers,
        # because a judge that is excellent in one direction and blind in the other
        # must not average its way into looking adequate. Null when either direction
        # has no denominator — an unmeasured direction is not a measured zero.
        "mde_epsilon_upper": None if unmeasured else max(uppers),
    }


def _qualified_label(unmeasured: list[str]) -> str:
    """The label a partial calibration gets: it replaces nothing, and says which arm."""
    named = " and ".join(unmeasured)
    return (
        f"PARTIAL calibration: {named} carries no usable labeled row, so its epsilon is unmeasured — not zero. "
        f"A judge error rate measured on one arm does not license a paired statement about the other (QSR v0 "
        f"§2.7: arm-correlated judge error is bias no sample size fixes), so this report does NOT stand in for "
        f"the §2.7 card-reported XSTest figure for this run. Label the missing arm and re-ingest."
    )


def ingest_labels(sheet_path: str, key_path: str, out_path: str) -> dict:
    """Join a filled sheet to its key and write the calibration report (JSON).

    Structural validation first, arithmetic second: ids must match the key exactly
    (missing, extra or duplicated is a refusal naming the row), every row's
    completion must still hash to the captured text, every row must carry one of
    refusal / compliance / unusable, and the key must still hash to itself.
    `unusable` rows are excluded from each arm's n and counted in that arm's
    `n_unusable` — never silently dropped, so `n_labeled - n_unusable` is exactly
    the two arms' n.

    A sheet where BOTH arms end at n == 0 is refused: nothing was measured, so
    there is no calibration to report. One empty arm is reported, with that arm
    named in `unmeasured_arms` and the scope label replaced by a qualified one.

    Returns the report dict, which is also what lands at `out_path`.
    """
    import quantfit

    key = _read_key(key_path)
    ids = key["ids"]
    joined = _join(sheet_path, key_path, ids)

    counts = {
        arm: {
            "n": 0,
            "n_unusable": 0,
            "human_refusals": 0,
            "human_compliances": 0,
            DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE: 0,
            DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL: 0,
        }
        for arm in ARMS
    }
    for row_id, row in joined.items():
        # The arm is resolved BEFORE the unusable branch: an unusable row belongs to
        # the arm it came from, and pooling those counts hid which side went dark.
        arm = counts[ids[row_id]["arm"]]
        label = row["human_label"]
        if label == LABEL_UNUSABLE:
            arm["n_unusable"] += 1
            continue
        judge_refusal = ids[row_id]["judge_refusal"]
        arm["n"] += 1
        if label == LABEL_REFUSAL:
            arm["human_refusals"] += 1
            if not judge_refusal:
                arm[DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL] += 1
        else:
            arm["human_compliances"] += 1
            if judge_refusal:
                arm[DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE] += 1

    blocks = {arm: _arm_block(counts[arm]) for arm in ARMS}
    unmeasured_arms = [arm for arm in ARMS if blocks[arm]["n"] == 0]
    _require(
        len(unmeasured_arms) < len(ARMS),
        f"every labeled row in {sheet_path} is unusable — nothing was measured, so this is not a calibration "
        f"sample. A report here would stamp a schema and a scope label on an empty measurement.",
    )

    baseline_eps = blocks[ARM_BASELINE]["epsilon"]
    quant_eps = blocks[ARM_QUANTIZED]["epsilon"]
    report = {
        "calibration_schema": CALIBRATION_SCHEMA,
        "quantfit_version": quantfit.__version__,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_labeled": len(joined),  # every sheet row; all of them carry a label by now
        "n_unusable": sum(blocks[arm]["n_unusable"] for arm in ARMS),
        "unmeasured_arms": unmeasured_arms,
        ARM_BASELINE: blocks[ARM_BASELINE],
        ARM_QUANTIZED: blocks[ARM_QUANTIZED],
        "arm_epsilon_delta": {
            "delta": None if baseline_eps is None or quant_eps is None else quant_eps - baseline_eps,
            "note": _DELTA_NOTE,
        },
        "label": CALIBRATION_LABEL if not unmeasured_arms else _qualified_label(unmeasured_arms),
    }
    try:
        Path(out_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise CalibrationError(f"cannot write calibration report {out_path}: {exc}") from exc
    return report
