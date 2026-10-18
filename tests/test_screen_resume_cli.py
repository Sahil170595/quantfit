"""Screen progress must not corrupt the single-document CLI JSON boundary."""

import json

import pytest

from quantfit import cli


@pytest.mark.parametrize("machine", [False, True])
def test_screen_progress_preserves_json_and_human_streams(monkeypatch, capsys, machine):
    def screen(*args, **kwargs):
        assert kwargs["resume"] is True
        print("resume: validated target")
        return {"rows": [], "by_stratum": {}}

    monkeypatch.setattr("quantfit.screen.run_screen", screen)
    args = ["screen", "--targets", "unused.json", "--out", "unused", "--resume"]
    assert cli.main([*args, *(["--json"] if machine else [])]) == 0
    captured = capsys.readouterr()
    if machine:
        assert json.loads(captured.out)["command"] == "screen"
        assert "resume: validated target" in captured.err
    else:
        assert "resume: validated target" in captured.out
        assert captured.err == ""


def test_resume_delegates_junit_to_held_execution_boundary(monkeypatch, tmp_path, capsys):
    output = tmp_path / "resume.xml"
    original = b"already published by held resume boundary"
    output.write_bytes(original)

    def screen(*args, **kwargs):
        assert kwargs["junit_path"] == str(output)
        return {"rows": [], "by_stratum": {}}

    monkeypatch.setattr("quantfit.screen.run_screen", screen)
    assert (
        cli.main(
            [
                "screen",
                "--targets",
                "unused.json",
                "--out",
                "unused",
                "--resume",
                "--junit",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["command"] == "screen"
    assert output.read_bytes() == original


@pytest.mark.parametrize("other,expected", [("no_regression", 4), ("regression", 3)])
def test_partial_execution_errors_cannot_become_a_clean_screen(monkeypatch, capsys, other, expected):
    from quantfit.screen import STATUS_ERROR

    summary = {
        "rows": [{"status": STATUS_ERROR}, {"status": other}],
        "by_stratum": {"gguf": {"refusal_robustness": {"n_measured": 1}, "over_refusal": {"n_measured": 1}}},
    }
    monkeypatch.setattr("quantfit.screen.run_screen", lambda *a, **kw: summary)
    code = cli.main(["screen", "--targets", "unused.json", "--out", "unused", "--resume", "--json"])
    assert code == expected
    assert json.loads(capsys.readouterr().out)["exit_code"] == expected


def test_strict_resume_notes_match_unverified_control_behavior(tmp_path, monkeypatch):
    from test_screen_resume import native_corpus, trap

    from quantfit.screen import CONDITIONALITY_LABEL, run_screen

    manifest, reports = native_corpus(tmp_path, [("clean", "gguf", 0, 0, None)], control="pass")
    calls = trap(monkeypatch)
    result = run_screen(str(manifest), str(reports), resume=True)
    assert calls == []
    assert result["by_stratum"]["gguf"]["refusal_robustness"]["conditionality"] == CONDITIONALITY_LABEL
    assert result["resume_receipt"]["control_evidence_verified"] is False
    notes = " ".join(result["notes"])
    assert "switches `conditionality` off" not in notes
    assert "No fresh execution" not in notes
    assert "unverified" in notes and "perfect-judge floor" in notes
