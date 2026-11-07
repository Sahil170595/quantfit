"""Portable file-loaded native local-source consumer; installed imports stay guarded."""

import importlib.util
from pathlib import Path


def test_complete_private_local_api_and_actual_os_cli_consumer(tmp_path):
    import quantfit

    checkout = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("local_probe_consumer", checkout / "tools/ci_probe_bundle.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    installed = not Path(quantfit.__file__).resolve().is_relative_to(checkout)
    result = helper.run(checkout, tmp_path / "controlled", installed=installed)
    assert result["n_profiles"] == 2
    assert {p["interface"] for p in result["profiles"]} == {"api", "cli"}
    assert [p["actual_os_cli_commands"] for p in result["profiles"]] == [0, 16]
    assert [p["whole_local_reads"] for p in result["profiles"]] == [4, 5]
    assert all(
        p["successful_execution_reads"] == 4 and p["arm_calls"] == 10 and p["deleted_source_replay"]
        for p in result["profiles"]
    )
