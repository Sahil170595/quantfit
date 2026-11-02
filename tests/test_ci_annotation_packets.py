import importlib.util
from pathlib import Path


def test_native_packet_producer_cli_collect_separate_ingestion(tmp_path):
    checkout = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("packet_consumer", checkout / "tools/ci_annotation_packets.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    result = helper.run(checkout, tmp_path)
    assert result["n_cases"] == 3 and result["n_parts"] == 9
    assert result["cases"][0]["baseline_n"] == result["cases"][0]["quantized_n"] == 4
    assert result["cases"][1]["schema2_schema3_arm_blocks_equal"]
    assert result["cases"][2]["both_ingestions_refused"]
    assert result["one_empty_arm"]["unmeasured_arms"] == ["baseline"]
    assert result["api_cli_page_bytes_equal"]
