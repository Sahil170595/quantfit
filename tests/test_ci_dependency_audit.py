"""Exercise the existing audit command's inventory, without advisory network calls."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _fixture(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "tools/ci_dependency_audit.py"
    spec = importlib.util.spec_from_file_location("dependency_audit_fixture", source)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    root = tmp_path / "checkout"
    (root / "tools/ci").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname="quantfit"\nversion="0.47.0"\n')
    (root / "tools/ci/pyproject.toml").write_text('[project]\nname="quantfit-hosted-validation"\nversion="0.0.0"\n')
    lock = root / "tools/ci/uv.lock"
    lock.write_text(
        "version=1\nrevision=5\n"
        '[[package]]\nname="quantfit-hosted-validation"\nversion="0.0.0"\nsource={virtual="."}\n'
        '[[package]]\nname="filelock"\nversion="3.20.3"\nsource={registry="https://pypi.org/simple"}\n'
        '[[package]]\nname="filelock"\nversion="4.2.1"\nsource={registry="https://pypi.org/simple"}\n'
        '[[package]]\nname="torch"\nversion="2.13.0+cpu"\nsource={registry="https://download.pytorch.org/whl/cpu"}\n'
    )
    helper.__file__ = str(root / "tools/ci_dependency_audit.py")
    monkeypatch.setattr(
        helper.importlib.metadata,
        "distributions",
        lambda: [
            SimpleNamespace(metadata={"Name": name}, version=version)
            for name, version in (("quantfit", "0.47.0"), ("filelock", "4.2.1"), ("torch", "2.13.0+cpu"))
        ],
    )
    batches = []
    helper.observed_calls = []

    def audit(argv, **kwargs):
        helper.observed_calls.append((argv, kwargs))
        batches.append(Path(argv[-1]).read_text().splitlines())
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(helper.subprocess, "run", audit)
    return helper, lock, batches


def test_every_universal_version_is_audited_alongside_installed(tmp_path, monkeypatch):
    helper, _, batches = _fixture(tmp_path, monkeypatch)
    helper.main()
    pairs = {pin for batch in batches for pin in batch}
    assert "filelock==4.2.1" in pairs and "torch==2.13.0" in pairs
    assert "filelock==3.20.3" in pairs
    assert len(batches) == 2
    assert all(len({pin.split("==")[0] for pin in batch}) == len(batch) for batch in batches)


@pytest.mark.parametrize("failed_layer", [1, 2])
@pytest.mark.parametrize("status", [1, 2])
def test_every_layer_attempted_and_any_native_failure_is_fatal(tmp_path, monkeypatch, failed_layer, status):
    helper, _, batches = _fixture(tmp_path, monkeypatch)
    original = helper.subprocess.run

    def fail(argv, **kwargs):
        original(argv, **kwargs)
        return subprocess.CompletedProcess(argv, status if len(batches) == failed_layer else 0)

    monkeypatch.setattr(helper.subprocess, "run", fail)
    with pytest.raises(SystemExit, match="1"):
        helper.main()
    assert len(batches) == 2
    for argv, kwargs in helper.observed_calls:
        assert all(flag in argv for flag in ("--strict", "--disable-pip", "--no-deps"))
        assert "--dry-run" not in argv and kwargs["check"] is False


def test_launch_failure_still_attempts_remaining_layer(tmp_path, monkeypatch):
    helper, _, batches = _fixture(tmp_path, monkeypatch)
    original = helper.subprocess.run

    def fail(argv, **kwargs):
        result = original(argv, **kwargs)
        if len(batches) == 1:
            raise OSError("fictional launch failure")
        return result

    monkeypatch.setattr(helper.subprocess, "run", fail)
    with pytest.raises(SystemExit, match="1"):
        helper.main()
    assert len(batches) == 2


def test_installed_only_pairs_dedup_roles_and_only_torch_cpu_is_mapped(tmp_path, monkeypatch):
    helper, _, batches = _fixture(tmp_path, monkeypatch)
    original = list(helper.importlib.metadata.distributions())
    monkeypatch.setattr(
        helper.importlib.metadata,
        "distributions",
        lambda: original + [SimpleNamespace(metadata={"Name": "other-package"}, version="1.0+cpu")],
    )
    inventory = helper._inventory()
    assert inventory[("filelock", "4.2.1")] == {"installed", "lock"}
    assert ("quantfit", "0.47.0") not in inventory
    assert ("quantfit-hosted-validation", "0.0.0") not in inventory
    helper.main()
    assert sum(pin == "filelock==4.2.1" for batch in batches for pin in batch) == 1
    assert "other-package==1.0+cpu" in {pin for batch in batches for pin in batch}


def test_partition_has_minimum_layers_and_no_version_lost(tmp_path, monkeypatch):
    helper, lock, batches = _fixture(tmp_path, monkeypatch)
    with lock.open("a") as stream:
        stream.write('[[package]]\nname="filelock"\nversion="4.2.2"\nsource={registry="https://pypi.org/simple"}\n')
    helper.main()
    assert len(batches) == 3
    assert {pin for batch in batches for pin in batch if pin.startswith("filelock==")} == {
        "filelock==3.20.3",
        "filelock==4.2.1",
        "filelock==4.2.2",
    }


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("version=1", "version=2"),
        ("version=1", "version=true"),
        ("revision=5", "revision=6"),
        ('version="3.20.3"', 'version="not-a-version"'),
        ('version="3.20.3"', ""),
        ('source={registry="https://pypi.org/simple"}', 'source={git="https://example.invalid/repo"}'),
        ('source={registry="https://pypi.org/simple"}', 'source={registry="https://example.invalid/simple"}'),
        ('name="quantfit-hosted-validation"', 'name="unexpected-virtual"'),
    ],
)
def test_unknown_schema_source_or_version_refuses_before_audit(tmp_path, monkeypatch, old, new):
    helper, lock, batches = _fixture(tmp_path, monkeypatch)
    lock.write_text(lock.read_text().replace(old, new, 1))
    with pytest.raises((ValueError, TypeError, KeyError)):
        helper.main()
    assert not batches


def test_missing_lock_cannot_be_a_clean_installed_only_audit(tmp_path, monkeypatch):
    helper, lock, batches = _fixture(tmp_path, monkeypatch)
    lock.unlink()
    with pytest.raises(FileNotFoundError):
        helper.main()
    assert not batches


def test_native_auditor_collection_rejects_conflict_but_accepts_layers(tmp_path):
    if importlib.util.find_spec("pip_audit") is None:
        pytest.skip("Native pip-audit collection requires the locked tooling profile")
    for index, pins in enumerate(("filelock==3.20.3\nfilelock==4.2.1\n", "filelock==3.20.3\n", "filelock==4.2.1\n")):
        path = tmp_path / f"layer-{index}.txt"
        path.write_text(pins)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--dry-run",
                "--strict",
                "--no-deps",
                "--disable-pip",
                "--progress-spinner",
                "off",
                "-r",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=30,
        )
        assert (result.returncode != 0) if index == 0 else (result.returncode == 0), result.stdout
