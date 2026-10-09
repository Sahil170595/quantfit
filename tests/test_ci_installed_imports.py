"""Bounded harness semantics, not a locally installed candidate qualification."""

import os
import shlex
import subprocess
import sys
from pathlib import Path

from tools.ci_installed import _pytest_code


def run(tmp_path, checkout, pythonpath):
    config = tmp_path / "pytest.ini"
    paths = pythonpath if isinstance(pythonpath, list) else [pythonpath] if pythonpath else []
    config.write_text(
        "[pytest]\npythonpath = " + " ".join(shlex.quote(p.as_posix()) for p in paths) + "\n", encoding="utf-8"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _pytest_code(checkout),
            "-c",
            str(config),
            "--import-mode=importlib",
            "-q",
            str(checkout / "tests/test_consumer.py"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        timeout=30,
    )


def fixture(tmp_path):
    checkout = tmp_path / "checkout"
    tests = checkout / "tests"
    tests.mkdir(parents=True)
    (tests / "bare_helper.py").write_text("VALUE = 42\n", encoding="utf-8")
    (tests / "test_consumer.py").write_text(
        "from bare_helper import VALUE\nimport quantfit\ndef test_fixture_import():\n    assert VALUE == 42\n",
        encoding="utf-8",
    )
    return checkout, tests


def test_sibling_helpers_need_only_tests_directory_with_importlib(tmp_path):
    checkout, tests = fixture(tmp_path)
    result = run(tmp_path, checkout, tests)
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"1 passed" in result.stdout


def test_bare_helpers_reproduce_collection_failure_without_test_path(tmp_path):
    checkout, _ = fixture(tmp_path)
    result = run(tmp_path, checkout, "")
    assert result.returncode != 0 and b"No module named 'bare_helper'" in result.stdout


def test_checkout_root_path_is_rejected_during_pytest_session(tmp_path):
    checkout, tests = fixture(tmp_path)
    result = run(tmp_path, checkout, [checkout, tests])
    assert result.returncode != 0 and b"checkout root injected into pytest" in result.stdout + result.stderr


def test_actual_source_package_origin_is_rejected_before_pytest(tmp_path):
    checkout = Path(__file__).resolve().parents[1]
    # Explicit source path is a negative harness case, not a supported consumer configuration.
    env = dict(os.environ, PYTHONPATH=str(checkout))
    result = subprocess.run(
        [sys.executable, "-c", _pytest_code(checkout)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode != 0 and b"checkout root injected into pytest" in result.stderr
