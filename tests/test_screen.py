"""0.5 screen harness — manifest validation + per-axis aggregation (hermetic, no model load).

Every test monkeypatches `quantfit.safety.verify.verify_safety` with a fake that
returns real `SafetyDrift` objects built by `_tabulate`, so the aggregation is
exercised against the actual drift vector, never a hand-written dict.
"""

import json

import pytest

from quantfit.safety.verify import wilson_interval
from quantfit.screen import CONDITIONALITY_LABEL, SUMMARY_FILENAME, ScreenError, run_screen

# --- drift fixtures: two probes, one per axis, so both axes are controllable ------


def _drift(baseline_flags, quant_flags):
    from quantfit.safety.verify import Probe, _tabulate

    probes = [Probe("u", "clear_unsafe", "unsafe"), Probe("s", "clear_safe", "safe")]
    return _tabulate(probes, baseline_flags, quant_flags)


def _clean():
    return _drift([True, False], [True, False])  # both axes at risk, nothing flipped


def _regressed():
    return _drift([True, False], [False, False])  # dangerous flip, both axes at risk


def _unmeasurable():
    return _drift([False, False], [False, False])  # baseline never refused: dangerous axis unmeasurable


def _regressed_with_unmeasurable_axis():
    return _drift([True, True], [False, True])  # dangerous flip; over-refusal axis has 0 at-risk pairs


# --- harness ---------------------------------------------------------------------


def _install(monkeypatch, outcomes):
    """Swap in a fake verify_safety keyed by the target's quant ref; returns the call log."""
    import quantfit.safety.verify as sv

    calls = []

    def fake(baseline, quant, token=None, max_new_tokens=64, report_path=None):
        calls.append(
            {
                "baseline": baseline,
                "quant": quant,
                "token": token,
                "max_new_tokens": max_new_tokens,
                "report_path": report_path,
            }
        )
        outcome = outcomes[quant]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(sv, "verify_safety", fake)
    return calls


def _entry(name, stratum="gguf", **overrides):
    entry = {"name": name, "stratum": stratum, "baseline": f"{name}-base", "quant": f"{name}-quant"}
    entry.update(overrides)
    return entry


def _manifest(tmp_path, targets, **overrides):
    payload = {"schema_version": 1, "name": "0.5 existence-proof hunt", "targets": targets}
    payload.update(overrides)
    p = tmp_path / "targets.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _rows_by_name(summary):
    return {r["name"]: r for r in summary["rows"]}


# --- aggregation -----------------------------------------------------------------


def test_aggregation_digits_per_stratum_and_axis(tmp_path, monkeypatch):
    # 3 GGUF targets with 1 dangerous flip, 2 compressed-tensors targets with 0 —
    # the bounds are the exact per-axis Wilson intervals, and neither strata nor
    # axes ever merge.
    entries = [_entry(f"g{i}") for i in range(3)] + [_entry(f"c{i}", "compressed-tensors") for i in range(2)]
    _install(
        monkeypatch,
        {
            "g0-quant": _regressed(),
            "g1-quant": _clean(),
            "g2-quant": _clean(),
            "c0-quant": _clean(),
            "c1-quant": _clean(),
        },
    )

    summary = run_screen(_manifest(tmp_path, entries), str(tmp_path / "out"))

    strata = summary["by_stratum"]
    assert set(strata) == {"gguf", "compressed-tensors"}
    assert "prevalence_bound_wilson95" not in summary  # never a pooled, screen-wide rate
    assert "prevalence_bound_wilson95" not in strata["gguf"]  # and never an axis-less one

    dangerous = strata["gguf"]["refusal_robustness"]
    assert (dangerous["n_measured"], dangerous["n_regressed"]) == (3, 1)
    assert dangerous["prevalence_bound_wilson95"] == list(wilson_interval(1, 3))
    assert dangerous["prevalence_bound_wilson95"] == pytest.approx([0.0614919447, 0.7923403992])

    overrefusal = strata["gguf"]["over_refusal"]
    assert (overrefusal["n_measured"], overrefusal["n_regressed"]) == (3, 0)
    assert overrefusal["prevalence_bound_wilson95"] == list(wilson_interval(0, 3))

    ct = strata["compressed-tensors"]
    assert (ct["n_targets"], ct["refusal_robustness"]["n_measured"], ct["refusal_robustness"]["n_regressed"]) == (
        2,
        2,
        0,
    )
    assert ct["refusal_robustness"]["prevalence_bound_wilson95"] == pytest.approx([0.0, 0.6576197725])

    assert summary["all_targets_attempted"] is True
    statuses = {name: row["status"] for name, row in _rows_by_name(summary).items()}
    assert statuses == {
        "g0": "regression",
        "g1": "no_regression",
        "g2": "no_regression",
        "c0": "no_regression",
        "c1": "no_regression",
    }


def test_row_carries_both_axes_and_the_verdict(tmp_path, monkeypatch):
    _install(monkeypatch, {"g0-quant": _regressed()})
    summary = run_screen(_manifest(tmp_path, [_entry("g0")]), str(tmp_path / "out"))

    row = summary["rows"][0]
    expected = _regressed().to_dict()
    assert row["verdict"] == expected["verdict"] and row["regression_detected"] is True
    assert row["unmeasurable_axes"] == []
    assert row["refusal_robustness"] == {
        "flips": 1,
        "at_risk": 1,
        "flip_rate_wilson95": list(wilson_interval(1, 1)),
        "mde_at_80pct_power": expected["refusal_robustness"]["mde_at_80pct_power"],
    }
    assert row["over_refusal"]["flips"] == 0 and row["over_refusal"]["at_risk"] == 1


def test_summary_carries_the_caps_as_data(tmp_path, monkeypatch):
    # QSR v0 §7: the caps are fields, not prose a reader can lose.
    _install(monkeypatch, {"g0-quant": _clean()})
    summary = run_screen(_manifest(tmp_path, [_entry("g0")]), str(tmp_path / "out"))
    assert set(summary["caps"]) == {"gguf", "compressed-tensors"}
    assert "16.5 GB" in summary["caps"]["gguf"] and "llama.cpp" in summary["caps"]["gguf"]
    assert "3B" in summary["caps"]["compressed-tensors"]


# --- operational-error isolation -------------------------------------------------


def test_operational_error_isolated_and_screen_continues(tmp_path, monkeypatch):
    # Target 2 of 3 blows up on a RuntimeError; 1 and 3 still run and aggregate.
    entries = [_entry("g0"), _entry("g1"), _entry("g2")]
    calls = _install(
        monkeypatch,
        {
            "g0-quant": _clean(),
            "g1-quant": RuntimeError("mispaired architectures"),
            "g2-quant": _clean(),
        },
    )

    summary = run_screen(_manifest(tmp_path, entries), str(tmp_path / "out"))

    assert [c["quant"] for c in calls] == ["g0-quant", "g1-quant", "g2-quant"]  # the break did not stop the loop
    rows = _rows_by_name(summary)
    assert rows["g1"] == {
        "name": "g1",
        "stratum": "gguf",
        "baseline": "g1-base",
        "quant": "g1-quant",
        "notes": None,
        "report": None,
        "status": "operational_error",
        "error": "mispaired architectures",
    }
    gguf = summary["by_stratum"]["gguf"]
    assert (gguf["n_targets"], gguf["n_completed"], gguf["n_operational_errors"]) == (3, 2, 1)
    dangerous = gguf["refusal_robustness"]
    assert (dangerous["n_measured"], dangerous["n_regressed"]) == (2, 0)  # the failed target is in no denominator
    assert dangerous["prevalence_bound_wilson95"] == list(wilson_interval(0, 2))


def test_oserror_is_absorbed_like_the_cli_exit_2_class(tmp_path, monkeypatch):
    # Gated/missing Hub repos surface as OSError subclasses (GatedRepoError), not
    # RuntimeError. The screen must absorb the same (RuntimeError, OSError) class
    # the CLI maps to exit 2 — one gated repo must not end a 10-target screen.
    entries = [_entry("g0"), _entry("g1"), _entry("g2")]
    calls = _install(
        monkeypatch,
        {
            "g0-quant": _clean(),
            "g1-quant": OSError("403 Client Error: access to org/model is restricted"),
            "g2-quant": _clean(),
        },
    )

    summary = run_screen(_manifest(tmp_path, entries), str(tmp_path / "out"))

    assert [c["quant"] for c in calls] == ["g0-quant", "g1-quant", "g2-quant"]
    rows = _rows_by_name(summary)
    assert rows["g1"]["status"] == "operational_error" and "restricted" in rows["g1"]["error"]
    assert summary["all_targets_attempted"] is True


def test_non_operational_error_propagates_and_leaves_a_partial_summary(tmp_path, monkeypatch):
    # Only the operational class is absorbed. A programming error surfaces raw —
    # but the targets that already ran stay on disk, marked partial.
    entries = [_entry("g0"), _entry("g1")]
    _install(monkeypatch, {"g0-quant": _clean(), "g1-quant": ValueError("bug in the harness")})
    out = tmp_path / "out"

    with pytest.raises(ValueError, match="bug in the harness"):
        run_screen(_manifest(tmp_path, entries), str(out))

    partial = json.loads((out / SUMMARY_FILENAME).read_text(encoding="utf-8"))
    assert partial["all_targets_attempted"] is False
    assert [r["name"] for r in partial["rows"]] == ["g0"]
    assert partial["manifest"]["n_targets"] == 2


def test_zero_measured_stratum_reports_the_unmeasured_bound(tmp_path, monkeypatch):
    # Every compressed-tensors target failed: (0.0, 1.0) means UNMEASURED, and the
    # summary says so in its own notes rather than leaving it to the reader.
    entries = [_entry("g0"), _entry("c0", "compressed-tensors")]
    _install(monkeypatch, {"g0-quant": _clean(), "c0-quant": RuntimeError("no such file: model-q4.gguf")})

    summary = run_screen(_manifest(tmp_path, entries), str(tmp_path / "out"))

    ct = summary["by_stratum"]["compressed-tensors"]
    for axis in ("refusal_robustness", "over_refusal"):
        assert (ct[axis]["n_measured"], ct[axis]["n_regressed"]) == (0, 0)
        assert ct[axis]["prevalence_bound_wilson95"] == [0.0, 1.0] == list(wilson_interval(0, 0))
    assert any("UNMEASURED" in note for note in summary["notes"])


# --- per-axis denominators ---------------------------------------------------------


def test_axis_unmeasurable_on_one_target_still_counts_the_other_axis(tmp_path, monkeypatch):
    entries = [_entry("g0"), _entry("g1")]
    _install(monkeypatch, {"g0-quant": _clean(), "g1-quant": _unmeasurable()})

    summary = run_screen(_manifest(tmp_path, entries), str(tmp_path / "out"))

    row = _rows_by_name(summary)["g1"]
    assert row["status"] == "unmeasurable"
    assert row["unmeasurable_axes"] == ["refusal-robustness"]
    assert row["refusal_robustness"]["at_risk"] == 0
    gguf = summary["by_stratum"]["gguf"]
    # dangerous axis: only g0 had at-risk pairs; over-refusal: both targets did.
    assert gguf["refusal_robustness"]["n_measured"] == 1
    assert gguf["over_refusal"]["n_measured"] == 2
    assert gguf["refusal_robustness"]["prevalence_bound_wilson95"] == list(wilson_interval(0, 1))
    assert gguf["over_refusal"]["prevalence_bound_wilson95"] == list(wilson_interval(0, 2))


def test_flip_on_a_partly_unmeasurable_target_enters_its_own_axis_bound(tmp_path, monkeypatch):
    # THE case the per-axis denominator exists for: a dangerous-axis flip on a
    # target whose over-refusal axis had no at-risk pairs. The flip must appear in
    # the dangerous-axis numerator AND denominator — a real detection never
    # vanishes from the headline number because the OTHER axis was unmeasurable.
    entries = [_entry("g0"), _entry("g1")]
    _install(monkeypatch, {"g0-quant": _clean(), "g1-quant": _regressed_with_unmeasurable_axis()})

    summary = run_screen(_manifest(tmp_path, entries), str(tmp_path / "out"))

    row = _rows_by_name(summary)["g1"]
    assert row["status"] == "regression" and row["unmeasurable_axes"] == ["over-refusal"]
    assert row["human_verified"] is None
    gguf = summary["by_stratum"]["gguf"]
    dangerous = gguf["refusal_robustness"]
    assert (dangerous["n_measured"], dangerous["n_regressed"]) == (2, 1)
    assert dangerous["prevalence_bound_wilson95"] == list(wilson_interval(1, 2))
    overrefusal = gguf["over_refusal"]
    assert (overrefusal["n_measured"], overrefusal["n_regressed"]) == (1, 0)


def test_flagged_and_verified_counts_are_separate(tmp_path, monkeypatch):
    # Bounds are flagged-basis; human verification is a separate, initially-zero count.
    entries = [_entry("g0"), _entry("g1")]
    _install(monkeypatch, {"g0-quant": _regressed(), "g1-quant": _clean()})

    summary = run_screen(_manifest(tmp_path, entries), str(tmp_path / "out"))

    rows = _rows_by_name(summary)
    assert rows["g0"]["human_verified"] is None  # null until a maintainer reads the pair
    assert "human_verified" not in rows["g1"]  # nothing to verify on a clean row
    dangerous = summary["by_stratum"]["gguf"]["refusal_robustness"]
    assert (dangerous["n_regressed"], dangerous["n_regressed_human_verified"]) == (1, 0)
    assert any("candidate" in note for note in summary["notes"])
    assert any("sensitivity control" in note for note in summary["notes"])


# --- sensitivity-control conditionality --------------------------------------------


def test_bounds_are_conditional_unless_the_control_passed(tmp_path, monkeypatch):
    # No sensitivity_control block: status defaults to not_run and EVERY bound
    # carries the ROADMAP label verbatim — the conditionality is machine-carried.
    _install(monkeypatch, {"g0-quant": _clean()})
    summary = run_screen(_manifest(tmp_path, [_entry("g0")]), str(tmp_path / "out"))

    assert summary["sensitivity_control"] == {"status": "not_run"}
    for axis in ("refusal_robustness", "over_refusal"):
        assert summary["by_stratum"]["gguf"][axis]["conditionality"] == CONDITIONALITY_LABEL


def test_passed_control_lifts_the_label_and_rides_in_the_summary(tmp_path, monkeypatch):
    _install(monkeypatch, {"g0-quant": _clean()})
    control = {"status": "pass", "report": "sensitivity-control.json", "human_verifier": "maintainer"}
    manifest = _manifest(tmp_path, [_entry("g0")], sensitivity_control=control)

    summary = run_screen(manifest, str(tmp_path / "out"))

    assert summary["sensitivity_control"] == control
    for axis in ("refusal_robustness", "over_refusal"):
        assert summary["by_stratum"]["gguf"][axis]["conditionality"] is None


def test_failed_control_keeps_the_label(tmp_path, monkeypatch):
    _install(monkeypatch, {"g0-quant": _clean()})
    manifest = _manifest(tmp_path, [_entry("g0")], sensitivity_control={"status": "fail"})
    summary = run_screen(manifest, str(tmp_path / "out"))
    assert summary["by_stratum"]["gguf"]["refusal_robustness"]["conditionality"] == CONDITIONALITY_LABEL


# --- plumbing --------------------------------------------------------------------


def test_report_path_and_decode_params_are_passed_through(tmp_path, monkeypatch):
    entries = [_entry("g0"), _entry("g1", notes="Q4_K_M vs F16, same binary")]
    calls = _install(monkeypatch, {"g0-quant": _clean(), "g1-quant": _clean()})
    out = tmp_path / "nested" / "out"

    summary = run_screen(_manifest(tmp_path, entries), str(out), token="hf_xyz", max_new_tokens=32)

    assert [c["report_path"] for c in calls] == [str(out / "g0.json"), str(out / "g1.json")]
    assert {c["token"] for c in calls} == {"hf_xyz"}
    assert {c["max_new_tokens"] for c in calls} == {32}
    assert [c["baseline"] for c in calls] == ["g0-base", "g1-base"]
    rows = _rows_by_name(summary)
    assert rows["g0"]["report"] == "g0.json"  # the filename, relative to out_dir
    assert rows["g1"]["notes"] == "Q4_K_M vs F16, same binary"
    assert summary["decode"] == {"max_new_tokens": 32}


def test_summary_on_disk_matches_the_returned_dict(tmp_path, monkeypatch):
    import quantfit

    _install(monkeypatch, {"g0-quant": _clean()})
    out = tmp_path / "out"

    summary = run_screen(_manifest(tmp_path, [_entry("g0")]), str(out))

    assert json.loads((out / SUMMARY_FILENAME).read_text(encoding="utf-8")) == summary
    assert summary["schema_version"] == 1
    assert summary["quantfit_version"] == quantfit.__version__
    assert summary["created_utc"].endswith("+00:00")  # UTC, explicit offset
    assert summary["manifest"]["name"] == "0.5 existence-proof hunt"


# --- manifest refusals -----------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"schema_version": 2, "name": "s", "targets": [_entry("g0")]}, "schema_version"),
        ({"name": "s", "targets": [_entry("g0")]}, "schema_version"),  # absent reads as wrong, never as v1
        ({"schema_version": 1, "targets": [_entry("g0")]}, "name must be"),
        ({"schema_version": 1, "name": "s", "targets": {"g0": {}}}, "non-empty list"),
        ({"schema_version": 1, "name": "s", "targets": []}, "non-empty list"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("g0"), _entry("g0")]}, "duplicate"),
        # case-insensitive filesystems: G0.json IS g0.json on Windows/macOS.
        ({"schema_version": 1, "name": "s", "targets": [_entry("g0"), _entry("G0")]}, "duplicate"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("g0", "awq")]}, "stratum"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("../evil")]}, "filesystem-safe"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("sub/dir")]}, "filesystem-safe"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("screen-summary")]}, "collides"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("Screen-Summary")]}, "collides"),
        ({"schema_version": 1, "name": "s", "targets": [{"name": "g0", "stratum": "gguf"}]}, "baseline must be"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("g0", quant_path="x")]}, "unknown keys"),
        ({"schema_version": 1, "name": "s", "targets": [_entry("g0", notes=7)]}, "notes"),
        ({"schema_version": 1, "name": "s", "targets": ["g0"]}, "not a JSON object"),
        # a typo'd top-level key (e.g. a misspelled sensitivity_control block) must
        # refuse loudly, never silently vanish.
        ({"schema_version": 1, "name": "s", "targets": [_entry("g0")], "sensitivity_ctrl": {}}, "unknown top-level"),
        (
            {"schema_version": 1, "name": "s", "targets": [_entry("g0")], "sensitivity_control": {"status": "ok"}},
            "sensitivity_control.status",
        ),
        (
            {"schema_version": 1, "name": "s", "targets": [_entry("g0")], "sensitivity_control": {"stat": "pass"}},
            "unknown keys",
        ),
        (
            {"schema_version": 1, "name": "s", "targets": [_entry("g0")], "sensitivity_control": "passed"},
            "JSON object",
        ),
    ],
)
def test_bad_manifest_refused(tmp_path, payload, match):
    p = tmp_path / "targets.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(ScreenError, match=match):
        run_screen(str(p), str(out))
    assert not out.exists()  # nothing is created until the manifest is understood


def test_unreadable_manifest_refused(tmp_path):
    bad = tmp_path / "targets.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ScreenError, match="unreadable target manifest"):
        run_screen(str(bad), str(tmp_path / "out"))


def test_missing_manifest_refused(tmp_path):
    with pytest.raises(ScreenError, match="unreadable target manifest"):
        run_screen(str(tmp_path / "nope.json"), str(tmp_path / "out"))


def test_manifest_that_is_not_an_object_refused(tmp_path):
    p = tmp_path / "targets.json"
    p.write_text(json.dumps([_entry("g0")]), encoding="utf-8")
    with pytest.raises(ScreenError, match="not a JSON object"):
        run_screen(str(p), str(tmp_path / "out"))


def test_screen_error_is_a_runtime_error():
    # The CLI's exit-2 handler catches RuntimeError; a ScreenError that is not one
    # would surface as a traceback instead of a clean operational failure.
    assert issubclass(ScreenError, RuntimeError)
