"""Screen transport dispatch keeps content verification separate from native flags."""

import json
import sys
from types import SimpleNamespace

import pytest

from quantfit.cli import main


@pytest.mark.parametrize("command", ["screen-create", "screen-verify"])
@pytest.mark.parametrize("receiving_code", [0, 3, 4])
def test_screen_bundle_cli_preserves_nested_verdict_without_changing_transport_exit(
    monkeypatch, capsys, command, receiving_code
):
    called = []
    result = {
        "kind": "quantfit.screen-bundle-verification",
        "status": "verified_content",
        "exit_code": 0,
        "receiving_summary": {"exit_code": receiving_code},
        "scope": "Byte binding does not authenticate execution or establish scientific GO.",
    }

    def create(*args):
        called.append(("create", args))
        return result

    def verify(*args):
        called.append(("verify", args))
        return result

    monkeypatch.setitem(
        sys.modules,
        "quantfit.screen_bundle",
        SimpleNamespace(create_screen_bundle=create, verify_screen_bundle=verify),
    )
    if command == "screen-create":
        args = ["--targets", "targets.json", "--reports-dir", "reports", "--out", "handoff"]
        expected = ("create", ("targets.json", "reports", "handoff"))
    else:
        args = ["--bundle", "relocated"]
        expected = ("verify", ("relocated",))
    assert main(["bundle", command, *args, "--json"]) == 0
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["command"] == "bundle " + command
    assert document["exit_code"] == 0 and document["result"] == result
    assert called == [expected] and captured.err == ""
