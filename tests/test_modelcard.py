"""Model-card fragment — deterministic render of a schema-v2 report (hermetic, no model load)."""

import json

import pytest

from quantfit.modelcard import model_card_fragment
from quantfit.safety.report import SCHEMA_VERSION, ArmRun, DriftReport, ReportError
from quantfit.safety.verify import detectable_flip_rate, wilson_interval

_TF_ENGINE = {"name": "transformers", "version": "5.10.1", "device": "cpu"}
_LCPP_ENGINE = {"name": "llama.cpp", "binary_sha256": "b" * 64, "source": "pinned", "threads": 8, "device": "cpu"}
_VERDICT = "NO REGRESSION DETECTED (dangerous-axis MDE ~13pp at n=12)"


def _axis(flips, at_risk, flip_key):
    # Stats come from the shipped estimators, so the expected digits below are a
    # claim about formatting, not a second implementation of the statistics.
    return {
        "at_risk": at_risk,
        flip_key: flips,
        "flip_rate_wilson95": list(wilson_interval(flips, at_risk)),
        "mde_at_80pct_power": detectable_flip_rate(at_risk),
    }


def _drift(dangerous=(0, 12), overrefusal=(2, 10), **overrides):
    unmeasurable = [
        name
        for name, (_, at_risk) in (("refusal-robustness", dangerous), ("over-refusal", overrefusal))
        if at_risk == 0
    ]
    fields = dict(
        n_probes=40,
        verdict=_VERDICT,
        regression_detected=bool(dangerous[0] or overrefusal[0]),
        unmeasurable_axes=unmeasurable,
        refusal_robustness=_axis(*dangerous, "harmful_compliance_regressions"),
        over_refusal=_axis(*overrefusal, "overrefusal_regressions"),
        by_zone={},
    )
    fields.update(overrides)
    return fields


def _arm(**overrides):
    fields = dict(
        model="m",
        revision="r1",
        resolved_dtype="torch.float16",
        runtime_s=1.0,
        engine=_TF_ENGINE,
        artifact_sha256=None,
    )
    fields.update(overrides)
    return ArmRun(**fields)


def _report(**overrides):
    fields = dict(
        schema_version=SCHEMA_VERSION,
        quantfit_version="0.5.0",
        created_utc="2026-07-24T00:00:00+00:00",
        judge={
            "id": "Crusadersk/quantsafe-refusal-modernbert",
            "revision": "b34061f964619a5b6e0ff24be45a428124fa36bc",
            "input_contract": "completion-only; truncated to 512 judge tokens; prompt never concatenated",
            "card_xstest_accuracy": 0.9773,
            "card_xstest_accuracy_label": (
                "card-reported, external XSTest/GPT-4 responses — uncalibrated, out-of-distribution for these probes"
            ),
        },
        probe_dataset={
            "id": "Crusadersk/quantsafe-judge-benchmark",
            "revision": "c26cc2e",
            "split": "train",
            "n_probes": 40,
        },
        decode={"max_new_tokens": 64, "do_sample": False, "chat_template": "model-default"},
        env={"python": "3.13.1", "torch": "2.9.0", "transformers": "5.10.1", "cuda": None, "device": "cpu"},
        baseline=_arm(model="org/base"),
        quantized=_arm(model="org/base-awq", revision=None, runtime_s=2.0),
        judge_runtime_s=0.5,
        drift=_drift(),
    )
    fields.update(overrides)
    return DriftReport(**fields)


def _gguf_report(**overrides):
    fields = dict(
        baseline=_arm(
            model="hf:org/repo/m-f16.gguf", resolved_dtype="F16", engine=_LCPP_ENGINE, artifact_sha256="a" * 64
        ),
        quantized=_arm(
            model="hf:org/repo/m-q4.gguf",
            revision=None,
            resolved_dtype="Q4_K_M",
            engine=_LCPP_ENGINE,
            artifact_sha256="c" * 64,
        ),
    )
    fields.update(overrides)
    return _report(**fields)


def _render(tmp_path, report, name="drift.json"):
    return model_card_fragment(str(report.to_json(str(tmp_path / name))))


def test_table_digits_match_the_drift_dict(tmp_path):
    # The shipped probe set's shape (0/12 dangerous, 2/10 over-refusal): one
    # decimal on percentages, whole pp on the MDE — exactly how verify.py prints.
    # Zero flips get no point estimate: verify.py's zero-flip branch deliberately
    # withholds the rate, so the card must not invent a skimmable "0.0%".
    md = _render(tmp_path, _report())
    assert "| 0/12 | -- | 0.0-24.2% | ~13pp |" in md
    assert "| 2/10 | 20.0% | 5.7-51.0% | ~15pp |" in md
    assert "| 0.0% |" not in md  # the zero-flip rate cell is withheld, not printed as 0.0%


def test_verdict_line_is_verbatim(tmp_path):
    from quantfit.safety.verify import Probe, _tabulate

    probes = [Probe("u", "clear_unsafe", "unsafe"), Probe("s", "clear_safe", "safe")]
    drift = _tabulate(probes, [True, False], [False, False]).to_dict()  # a real dangerous flip
    md = _render(tmp_path, _report(drift=drift))
    assert f"**Verdict: {drift['verdict']}**" in md
    assert "REGRESSION DETECTED (dangerous axis)" in md  # not paraphrased on the way out


def test_transformers_arm_gets_the_vllm_serve_line(tmp_path):
    md = _render(tmp_path, _report())
    assert "vllm serve org/base-awq" in md
    assert "llama-server" not in md
    assert "transformers `5.10.1`" in md


def test_gguf_arm_gets_the_llama_server_line_and_binary_hash(tmp_path):
    md = _render(tmp_path, _gguf_report())
    assert "llama-server -m hf:org/repo/m-q4.gguf" in md
    assert "vllm serve" not in md
    assert _LCPP_ENGINE["binary_sha256"] in md
    assert "same-binary mandate" in md
    assert "`Q4_K_M`" in md and "`F16`" in md
    assert "a" * 64 in md and "c" * 64 in md  # both artifact hashes ride along


def test_mismatched_binary_hashes_are_called_out(tmp_path):
    # The mandate is auditable only if an unequal pair reads as a failure, not silence.
    other = dict(_LCPP_ENGINE, binary_sha256="d" * 64)
    md = _render(tmp_path, _gguf_report(quantized=_arm(model="q.gguf", resolved_dtype="Q4_K_M", engine=other)))
    assert "**The two arms record different `binary_sha256` values.**" in md


def test_missing_binary_hashes_read_as_unverifiable_not_mismatched(tmp_path):
    # Missing != mismatched: two absent hashes must not render "different values"
    # two lines under "not recorded" — that is a self-contradicting safety card.
    hashless = {"name": "llama.cpp", "source": "user build", "threads": 8, "device": "cpu"}
    md = _render(
        tmp_path,
        _gguf_report(
            baseline=_arm(model="b.gguf", resolved_dtype="F16", engine=hashless),
            quantized=_arm(model="q.gguf", revision=None, resolved_dtype="Q4_K_M", engine=hashless),
        ),
    )
    assert "cannot be" in md and "verified from this report" in md
    assert "record different `binary_sha256` values" not in md


def test_unknown_engine_gets_a_note_never_a_silent_omission(tmp_path):
    other = {"name": "vllm", "version": "0.9"}
    md = _render(tmp_path, _report(quantized=_arm(model="q", revision=None, engine=other)))
    assert "records no serve command for engine `vllm`" in md
    assert "vllm serve" not in md and "llama-server" not in md
    assert md.count("```") == 0  # a note, not an empty fence


def test_unmeasurable_axis_is_warned_about(tmp_path):
    drift = _drift(
        dangerous=(0, 0), verdict="NO REGRESSION DETECTED (refusal-robustness unmeasurable: 0 at-risk pairs)"
    )
    md = _render(tmp_path, _report(drift=drift))
    assert "**Not measured: refusal-robustness.**" in md
    assert "exit 4 means *nothing was measured on that axis*, not a pass" in md
    assert "| 0/0 | n/a | n/a | n/a |" in md  # no fabricated rate on an axis with no at-risk pairs


def test_warning_derives_from_at_risk_not_from_the_reported_list(tmp_path):
    # A hand-edited report where unmeasurable_axes disagrees with at_risk == 0 must
    # still warn: the table row and the warning read the SAME field, so they can't
    # split — a 0/0 row with no exit-4 language is the overstatement this closes.
    drift = _drift(dangerous=(0, 0))
    drift["unmeasurable_axes"] = []  # tampered: the list lies, the counts don't
    md = _render(tmp_path, _report(drift=drift))
    assert "**Not measured: refusal-robustness.**" in md


def test_no_unmeasurable_warning_when_both_axes_measured(tmp_path):
    md = _render(tmp_path, _report())
    assert "Not measured" not in md
    assert "exit" not in md


def test_provenance_carries_pins_and_the_uncalibrated_label(tmp_path):
    md = _render(tmp_path, _report())
    assert "b34061f964619a5b6e0ff24be45a428124fa36bc" in md
    assert "c26cc2e" in md and "n=40" in md
    assert "`max_new_tokens` = 64" in md and "`do_sample` = False" in md
    assert "card accuracy 0.9773" in md
    assert "uncalibrated, out-of-distribution for these probes" in md  # verbatim, never dropped
    assert "`0.5.0`" in md and "2026-07-24T00:00:00+00:00" in md
    assert "none (local artifact, no Hub commit)" in md  # the quantized arm has no revision


def test_footer_states_the_bound_on_a_no_detection_report(tmp_path):
    clean = _drift(overrefusal=(0, 10))  # nothing flipped on either axis
    md = _render(tmp_path, _report(drift=clean))
    assert "Measured over 40 curated probes; a no-detection result bounds the drift, it does not certify safety." in md


def test_footer_on_a_detection_never_uses_no_detection_language(tmp_path):
    # The default fixture HAS flips (2/10 over-refusal): hedging in "no-detection
    # result" language under a detected regression is a non-sequitur on a card.
    md = _render(tmp_path, _report())
    assert "a no-detection result bounds the drift" not in md
    assert "candidates until human-verified" in md
    assert "does not certify safety" in md


def test_caps_line_matches_the_measurement_class(tmp_path):
    tf = _render(tmp_path, _report())
    assert "Scale cap for this measurement class (QSR v0 §7)" in tf and "3B parameters in-GPU" in tf
    gguf = _render(tmp_path, _gguf_report(), "g.json")
    assert "16.5 GB" in gguf and "one pinned llama.cpp binary" in gguf


def test_render_is_deterministic(tmp_path):
    report = _report()
    path = str(report.to_json(str(tmp_path / "drift.json")))
    assert model_card_fragment(path) == model_card_fragment(path)


def test_no_safety_tax_string_anywhere(tmp_path):
    for report in (_report(), _gguf_report()):
        md = _render(tmp_path, report).lower()
        assert "safety tax" not in md
        assert "tax" not in md


def test_fragment_shape_is_a_pasteable_section(tmp_path):
    for name, report in (("tf", _report()), ("gguf", _gguf_report())):
        md = _render(tmp_path, report, name + ".json")
        assert md.startswith("## Quantization safety drift (QSR v0)\n")
        assert md.endswith("\n") and not md.endswith("\n\n")
        assert 38 <= len(md.splitlines()) <= 60  # a card section someone will paste, not a report dump
        assert md.count("```") == 2  # exactly one fenced serve block


def test_malformed_report_raises_report_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReportError, match="unreadable"):
        model_card_fragment(str(bad))


def test_wrong_schema_report_raises_report_error(tmp_path):
    p = _report().to_json(str(tmp_path / "drift.json"))
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["schema_version"] = 1  # a 0.4.0 report
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReportError, match="schema_version"):
        model_card_fragment(str(p))


def test_report_too_thin_to_render_is_a_clean_refusal(tmp_path):
    # schema v2 checks that `drift` IS an object, not what is in it — a report
    # missing an axis must refuse operationally, not raise KeyError at the user.
    thin = _report(drift={"n_probes": 40, "verdict": "NO REGRESSION DETECTED"})
    with pytest.raises(ReportError, match="lacks a field"):
        _render(tmp_path, thin)


@pytest.mark.parametrize(
    "tamper",
    [
        {"flip_rate_wilson95": [0.1, 0.2, 0.3]},  # wrong arity -> ValueError on unpack
        {"mde_at_80pct_power": "0.15"},  # stringly number -> ValueError in the formatter
    ],
)
def test_schema_valid_but_garbled_drift_is_a_clean_refusal(tmp_path, tamper):
    # cli.main catches only (RuntimeError, OSError): a ValueError escaping here
    # would traceback raw at the user from a tampered-but-schema-valid report.
    drift = _drift()
    drift["over_refusal"] = {**drift["over_refusal"], **tamper}
    with pytest.raises(ReportError, match="lacks a field"):
        _render(tmp_path, _report(drift=drift))
