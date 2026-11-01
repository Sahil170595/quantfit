import importlib.util
from pathlib import Path


def test_complete_controlled_corpus_native_consumer(tmp_path):
    import quantfit

    checkout = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("probe_corpus_consumer", checkout / "tools/ci_probe_corpus.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    installed = not Path(quantfit.__file__).resolve().is_relative_to(checkout)
    result = helper.run(checkout, tmp_path, installed=installed)
    assert result["positive_cases"] == 16 and result["actual_source_load_once"]
    assert {case["native_exit"] for case in result["cases"]} == {0, 3, 4}
