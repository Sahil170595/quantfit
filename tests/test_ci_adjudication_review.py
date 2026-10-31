import importlib.util
from pathlib import Path


def test_native_private_page_source_consumer(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("private_review_acceptance", root / "tools/ci_adjudication_review.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    result = helper.run(root, tmp_path)
    assert result["positive_cases"] == len(result["cases"]) == 12
    assert result["adverse_cases"] == len(result["adverse"]) == 16
    assert result["transport"] == "stdlib quote-all CSV fixture, NOT browser execution"
