"""Finite hypothetical grid, native nonmonotonicity and before-math work admission."""

import json
from pathlib import Path

import pytest
from test_resolution import resolution_fixture


def test_opt_in_complete_grid_preserves_actual_report_and_native_axes(tmp_path):
    from quantfit.resolution import analyze_resolution
    from quantfit.resolution_budget import ResolutionBudget

    report, calibration = resolution_fixture(tmp_path)
    before = (report.read_bytes(), Path(calibration).read_bytes())
    actual = analyze_resolution(str(report), calibration)
    result = analyze_resolution(
        str(report), calibration, str(tmp_path / "planned.json"), planning=ResolutionBudget(0, 80, 100.0, (30.0,))
    )
    assert result["axes"] == actual["axes"] and result["inputs"] == actual["inputs"]
    assert result["binding_fingerprint"] == actual["binding_fingerprint"]
    assert (report.read_bytes(), Path(calibration).read_bytes()) == before
    plan = result["planning"]
    assert plan["hypothetical"] is True and len(plan["curve"]) == 81
    assert [row["n_at_risk"] for row in plan["curve"]] == list(range(81))
    assert all(not row["passes"] for row in plan["curve"] if not row["detectable_at_target_power"])
    assert [axis["n_at_risk"] for axis in result["axes"].values()] == [10, 24]
    assert "planning" not in actual and "verdict" not in result


def test_known_native_nonmonotone_grid_has_isolated_pass_not_stable_suffix():
    from quantfit.resolution_budget import ResolutionBudget, _curve, _summary
    from quantfit.safety.mde import effective_mde, power_at

    rows = _curve(ResolutionBudget(6, 7, 50.0, (30.0,)), 0.055)
    assert [row["passes"] for row in rows] == [True, False]
    for row in rows:
        n = row["n_at_risk"]
        assert row["effective_mde"] == effective_mde(n, 0.055)
        assert row["power_at_requested"][0]["power"] == power_at(0.30, n, 0.055)
    summary = _summary(rows)
    assert summary == {
        "first_passing_n": 6,
        "feasible_runs": [{"n_min": 6, "n_max": 6}],
        "stable_suffix": None,
        "no_feasible_point": False,
    }


@pytest.mark.parametrize("n_min,n_max", [(0, 0), (0, 16), (10, 12)])
def test_saturated_error_mde_sentinel_cannot_pass_100pp(n_min, n_max):
    from quantfit.resolution_budget import ResolutionBudget, _curve, _summary

    rows = _curve(ResolutionBudget(n_min, n_max, 100.0), 1.0)
    assert all(row["effective_mde"] == 1.0 and not row["passes"] for row in rows)
    assert _summary(rows)["no_feasible_point"] is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_min": True},
        {"n_max": 1.0},
        {"n_min": -1},
        {"n_min": 10, "n_max": 9},
        {"n_max": 999999999999},
        {"max_mde_pp": float("nan")},
        {"max_mde_pp": 0},
        {"max_mde_pp": 101},
        {"effects_pp": (30.0, 30.0)},
        {"effects_pp": (float("inf"),)},
        {"effects_pp": (True,)},
        {"effects_pp": (1.0,) * 9},
    ],
)
def test_all_options_are_admitted_before_io(tmp_path, monkeypatch, kwargs):
    import quantfit.resolution_budget as budget
    from quantfit.resolution import ResolutionError, analyze_resolution

    def forbidden(*args, **kwargs):
        raise AssertionError("IO happened before option admission")

    monkeypatch.setattr(budget, "hold", forbidden)
    values = {"n_min": 0, "n_max": 4, "max_mde_pp": 50.0, **kwargs}
    with pytest.raises(ResolutionError):
        analyze_resolution("missing-report", "missing-calibration", planning=budget.ResolutionBudget(**values))


def test_combined_actual_and_full_grid_budget_refuses_before_any_math(tmp_path, monkeypatch):
    import quantfit.resolution_budget as budget
    from quantfit import resolution

    report, calibration = resolution_fixture(tmp_path)
    monkeypatch.setattr(budget, "MAX_WORK_UNITS", 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("native power/threshold/MDE ran before whole-work admission")

    monkeypatch.setattr(resolution, "mde_block", forbidden)
    monkeypatch.setattr(budget, "detection_threshold", forbidden)
    monkeypatch.setattr(budget, "_power", forbidden)
    monkeypatch.setattr(budget, "_effective_mde_at", forbidden)
    with pytest.raises(resolution.ResolutionError):
        resolution.analyze_resolution(
            str(report), calibration, str(tmp_path / "out.json"), planning=budget.ResolutionBudget(0, 80, 100.0)
        )
    assert not (tmp_path / "out.json").exists()


def test_exact_threshold_cache_and_all_power_terms_are_charged(tmp_path, monkeypatch):
    import quantfit.resolution_budget as budget
    from quantfit.resolution import analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    calls = []
    native = budget.detection_threshold

    def threshold(n, q, alpha):
        calls.append((n, q, alpha))
        return native(n, q, alpha)

    monkeypatch.setattr(budget, "detection_threshold", threshold)
    result = analyze_resolution(str(report), calibration, planning=budget.ResolutionBudget(0, 16, 100.0, (30.0, 40.0)))
    assert len(calls) == len(set(calls)) == 17
    admission = result["planning"]["work_admission"]
    actual = sum(3 * (n * (n + 1) // 2 + n + 1) + 127 * (n + 1) for n in (10, 24))
    planned = sum(n * (n + 1) // 2 + n + 1 + 68 * (n + 1) for n in range(17))
    assert admission["actual_upper_bound"] == actual
    assert admission["planned_upper_bound"] == planned
    assert admission["total_upper_bound"] == actual + planned <= admission["limit"]


def test_work_cap_accepts_one_full_native_size_and_refuses_late_high_grid_before_math(tmp_path, monkeypatch):
    import quantfit.resolution_budget as budget
    from quantfit import resolution

    one = budget._work(
        budget.ResolutionBudget(4096, 4096, 100.0, tuple(range(8))), {"a": {"n_at_risk": 4096}, "b": {"n_at_risk": 0}}
    )
    assert one["total_upper_bound"] == 34_402_639 < budget.MAX_WORK_UNITS
    report, calibration = resolution_fixture(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("late high-grid refusal happened after native math")

    monkeypatch.setattr(resolution, "mde_block", forbidden)
    monkeypatch.setattr(budget, "detection_threshold", forbidden)
    monkeypatch.setattr(budget, "_power", forbidden)
    monkeypatch.setattr(budget, "_effective_mde_at", forbidden)
    with pytest.raises(resolution.ResolutionError):
        resolution.analyze_resolution(str(report), calibration, planning=budget.ResolutionBudget(3841, 4096, 50.0))


def test_complete_finite_runs_and_suffix_match_direct_native_scan():
    from quantfit.resolution_budget import ResolutionBudget, _curve, _summary
    from quantfit.safety.mde import effective_mde, power_at

    rows = _curve(ResolutionBudget(0, 30, 50.0), 0.055)
    feasible = {n for n in range(31) if power_at(1.0, n, 0.055) >= 0.8 and effective_mde(n, 0.055) <= 0.5}
    summary = _summary(rows)
    represented = {n for run in summary["feasible_runs"] for n in range(run["n_min"], run["n_max"] + 1)}
    assert represented == feasible and summary["first_passing_n"] == min(feasible)
    suffix = summary["stable_suffix"]
    assert suffix["n_max"] == 30 and all(n in feasible for n in range(suffix["n_min"], 31))
    assert suffix["n_min"] == 0 or suffix["n_min"] - 1 not in feasible


@pytest.mark.parametrize("role", [0, 1])
def test_planned_output_protects_actual_inputs_and_existing_files(tmp_path, role):
    from quantfit.resolution import ResolutionError, analyze_resolution
    from quantfit.resolution_budget import ResolutionBudget

    report, calibration = resolution_fixture(tmp_path)
    original = [report.read_bytes(), Path(calibration).read_bytes()]
    with pytest.raises(ResolutionError):
        analyze_resolution(
            str(report), calibration, (str(report), calibration)[role], planning=ResolutionBudget(0, 4, 100.0)
        )
    assert [report.read_bytes(), Path(calibration).read_bytes()] == original
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"existing")
    with pytest.raises(ResolutionError):
        analyze_resolution(str(report), calibration, str(existing), planning=ResolutionBudget(0, 4, 100.0))
    assert existing.read_bytes() == b"existing"


def test_path_inputs_held_once_and_bytes_and_input_adapters_agree(tmp_path, monkeypatch):
    import quantfit.resolution_budget as budget
    from quantfit.resolution import analyze_resolution, analyze_resolution_bytes, analyze_resolution_inputs

    report, calibration = resolution_fixture(tmp_path, unmeasurable=True)
    calls = []
    native = budget.hold

    def held(path, limit):
        calls.append(path)
        return native(path, limit)

    monkeypatch.setattr(budget, "hold", held)
    plan = budget.ResolutionBudget(0, 16, 100.0)
    result = analyze_resolution(str(report), calibration, planning=plan)
    assert calls == [str(report), calibration]
    assert result["axes"]["refusal-robustness"]["n_at_risk"] == 0
    assert result["axes"]["refusal-robustness"]["detectable_at_target_power"] is False
    _, from_bytes = analyze_resolution_bytes(report.read_bytes(), Path(calibration).read_bytes(), planning=plan)
    _, from_inputs = analyze_resolution_inputs(str(report), calibration, planning=plan)
    for value in (from_bytes, from_inputs):
        assert {k: v for k, v in value.items() if k != "created_utc"} == {
            k: v for k, v in result.items() if k != "created_utc"
        }


@pytest.mark.parametrize("mutation", ["source", "output"])
def test_late_source_change_and_output_race_refuse(tmp_path, monkeypatch, mutation):
    import quantfit.resolution_budget as budget
    from quantfit.resolution import ResolutionError, analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    native = budget.publish

    def raced(outputs, inputs):
        if mutation == "source":
            report.write_bytes(report.read_bytes() + b"\n")
        else:
            out.write_bytes(b"existing")
        return native(outputs, inputs)

    monkeypatch.setattr(budget, "publish", raced)
    out = tmp_path / "out.json"
    with pytest.raises(ResolutionError):
        analyze_resolution(str(report), calibration, str(out), planning=budget.ResolutionBudget(0, 4, 100.0))
    assert out.read_bytes() == b"existing" if mutation == "output" else not out.exists()


def test_changed_actual_scope_is_refused_before_any_actual_or_grid_math(tmp_path, monkeypatch):
    import quantfit.resolution_budget as budget
    from quantfit import resolution

    report, calibration = resolution_fixture(tmp_path)
    payload = json.loads(report.read_bytes())
    payload["baseline"]["revision"] = "c" * 40
    report.write_text(json.dumps(payload), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("scope refusal happened after native math")

    monkeypatch.setattr(resolution, "mde_block", forbidden)
    monkeypatch.setattr(budget, "detection_threshold", forbidden)
    monkeypatch.setattr(budget, "_power", forbidden)
    monkeypatch.setattr(budget, "_effective_mde_at", forbidden)
    with pytest.raises(resolution.ResolutionError):
        resolution.analyze_resolution(str(report), calibration, planning=budget.ResolutionBudget(0, 4, 100.0))


def test_curve_does_not_call_public_calculators_or_rederive_hidden_thresholds(monkeypatch):
    from quantfit import resolution_budget as budget
    from quantfit.safety import mde

    def forbidden(*args, **kwargs):
        raise AssertionError("planned curve used an uncharged public calculator/threshold")

    # Budget retains its already imported native threshold function. Public native
    # power/MDE/block aliases would call mde.detection_threshold and fail here,
    # including aliases imported before this test's monkeypatch.
    with monkeypatch.context() as patch:
        for name in ("power_at", "effective_mde", "mde_block", "detection_threshold"):
            patch.setattr(mde, name, forbidden)
        rows = budget._curve(budget.ResolutionBudget(6, 7, 50.0), 0.055)
    assert [row["effective_mde"] for row in rows] == [mde.effective_mde(n, 0.055) for n in (6, 7)]


@pytest.mark.parametrize(
    "values", [["--plan-effect", "30"], ["--plan-n-min", "0"], ["--plan-n-max", "10", "--plan-mde-pp", "50"]]
)
def test_partial_cli_options_refuse_before_reading(values, tmp_path):
    from quantfit.cli import main

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "resolution",
                "--report",
                "missing",
                "--calibration-report",
                "missing",
                "--out",
                str(tmp_path / "out.json"),
                *values,
            ]
        )
    assert exc.value.code == 2 and not (tmp_path / "out.json").exists()
