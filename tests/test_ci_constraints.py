"""Bounded manual-install constraints helper, tested against public package metadata.

Baseline CI now installs the complete hash-locked validation graph. The old workflow
text assertions about generating a constraints file in each job were removed because
they described a retired install path. The generator remains available for manual
subset installs; these tests exercise its actual output, errors, and parent caps.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

from packaging.specifiers import SpecifierSet

try:  # stdlib on 3.11+
    import tomllib
except ModuleNotFoundError:  # 3.10: pytest declares `tomli>=1` there
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parent.parent
_TOOL_PATH = _ROOT / "tools" / "ci_constraints.py"
_PYPROJECT = _ROOT / "pyproject.toml"

_CONSTRAINTS_FILE = "ci-constraints.txt"


def _run_tool(*args, cwd=None) -> subprocess.CompletedProcess:
    """Run the generator as a child process, decoding its output explicitly.

    `text=True` alone decodes with the caller's locale encoding, so a Windows box whose
    console codepage is cp1252 and whose pytest runs UTF-8 raises UnicodeDecodeError in
    subprocess's reader thread — the test then fails on the harness, not on the tool.
    `errors="replace"` keeps that from ever being a false failure again; the tool's own
    output being ASCII (asserted below) is what makes the point moot in practice.
    """
    return subprocess.run(
        [sys.executable, str(_TOOL_PATH), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,  # a non-zero exit is the subject of several tests, not an error here
    )


def _load_tool():
    """Import the tool by path: it is a script in tools/, not an installed module."""
    spec = importlib.util.spec_from_file_location("quantfit_ci_constraints", _TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cc = _load_tool()


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def _declared_requirements() -> dict[str, str]:
    """{canonical name: requirement string} across dependencies + every extra."""
    project = _pyproject()["project"]
    out: dict[str, str] = {}
    for requirement in project.get("dependencies", []):
        out[cc.normalize(cc.requirement_name(requirement))] = requirement.strip()
    for requirements in project.get("optional-dependencies", {}).values():
        for requirement in requirements:
            out[cc.normalize(cc.requirement_name(requirement))] = requirement.strip()
    return out


def _capped_packages() -> set[str]:
    """Names pyproject bounds from above — the ones a bare `pip install` can violate."""
    return {name for name, req in _declared_requirements().items() if re.search(r"(?:<|<=|==|~=)\s*\d", req)}


# --------------------------------------------------------------------------------
# 1. The generator reproduces pyproject
# --------------------------------------------------------------------------------


def test_generated_constraints_cover_every_declared_requirement():
    emitted = cc.collect(_pyproject())
    expected = dict(_declared_requirements())
    for name, (cap, _parent) in cc.INHERITED_CAPS.items():
        expected[name] = f"{expected[name]},{cap}"
    assert emitted == expected, (
        "the constraints file must carry every requirement pyproject declares — a package "
        "omitted here is a package CI can install at any version. Diff: "
        f"missing={sorted(set(_declared_requirements()) - set(emitted))}, "
        f"unexpected={sorted(set(emitted) - set(_declared_requirements()))}"
    )


def test_the_caps_that_motivated_this_tool_are_actually_emitted():
    """A floor, so the check keeps meaning if the generic comparison above is ever loosened."""
    emitted = cc.collect(_pyproject())
    for name in ("gguf", "inspect-ai", "ruff"):
        assert name in emitted, f"{name} is missing from the generated constraints"
        bounds = SpecifierSet(emitted[name][len(name) :])
        assert any(spec.operator in {"<", "<=", "==", "~="} for spec in bounds), (
            f"{name} is emitted as {emitted[name]!r} with no upper bound. It carried one when this "
            "tool was written; if the cap was removed on purpose, say so in pyproject and in "
            "tests/test_dependencies.py:_EXEMPTIONS rather than only here."
        )
    # The observed extension is deliberately narrower than a minor cap. Prove
    # the emitted constraint admits its actual SDK and refuses both neighbours.
    from quantfit.inspect_task import VERIFIED_INSPECT_AI_VERSION

    assert emitted["inspect-ai"] == f"inspect-ai=={VERIFIED_INSPECT_AI_VERSION}"
    sdk = SpecifierSet(emitted["inspect-ai"][len("inspect-ai") :])
    assert sdk.contains("0.3.269") and not sdk.contains("0.3.252") and not sdk.contains("0.3.270")


def test_an_inherited_cap_is_emitted_for_a_dependency_pyproject_bounds_only_through_a_parent():
    """huggingface_hub 2.0.0 reached CI's unit job on 2026-09-25 because that job installs
    it WITHOUT transformers, the parent that caps it at <2.0 in every real install."""
    emitted = cc.collect(_pyproject())
    assert emitted["huggingface-hub"].endswith(",<2.0"), emitted["huggingface-hub"]


def test_every_inherited_cap_names_a_parent_bounded_exemption():
    """An inherited cap is only legitimate for a dependency pyproject deliberately leaves
    uncapped BECAUSE a parent caps it. Anything else belongs in pyproject itself."""
    spec = importlib.util.spec_from_file_location(
        "quantfit_test_dependencies", _ROOT / "tests" / "test_dependencies.py"
    )
    assert spec and spec.loader
    deps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deps)
    _EXEMPTIONS = deps._EXEMPTIONS

    for name, (_cap, parent) in cc.INHERITED_CAPS.items():
        exemption = _EXEMPTIONS.get(name)
        assert exemption is not None and exemption.kind == "PARENT_BOUNDED", (
            f"{name} carries an inherited CI cap but is not a PARENT_BOUNDED exemption"
        )
        assert parent in exemption.chain or parent == exemption.chain[-1], (
            f"{name}'s inherited cap cites {parent!r}, which is not in its exemption chain {exemption.chain}"
        )


def test_the_inherited_cap_is_still_what_the_installed_parent_declares():
    """The one hand-recorded value in this tool, checked against the parent's own metadata
    wherever the parent is installed. If transformers ever lifts its huggingface-hub cap,
    this fails rather than letting CI keep testing a ceiling nothing imposes any more."""
    import importlib.metadata as md

    checked = 0
    for name, (cap, parent) in cc.INHERITED_CAPS.items():
        try:
            requires = md.requires(parent) or []
        except md.PackageNotFoundError:
            continue
        checked += 1
        declared = [r for r in requires if cc.requirement_name(r.split(";")[0]) == name]
        assert declared, f"{parent} no longer declares {name} at all"
        assert any(cap.replace(" ", "") in r.replace(" ", "") for r in declared), (
            f"{parent} declares {declared} for {name}; the recorded inherited cap is {cap!r}"
        )
    if not checked:
        import pytest

        pytest.skip("no parent that imposes an inherited cap is installed here (CI's unit job)")


def test_rendered_file_is_one_requirement_per_line_and_pip_readable():
    text = cc.render(cc.collect(_pyproject()), _PYPROJECT)
    body = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert body == sorted(body), "requirements should be emitted in a stable sorted order"
    assert len(body) == len(set(body)), f"duplicate constraint lines: {body}"
    for line in body:
        # pip rejects both of these in a constraints file; catching them here beats
        # catching them in a CI step that has already spent two minutes installing.
        assert "[" not in line, f"constraints cannot carry extras: {line!r}"
        assert not line.startswith("-"), f"constraints cannot carry options: {line!r}"


def test_everything_the_tool_prints_is_ascii():
    """Its output is machine-consumed, and stdout's encoding on Windows is the console
    codepage while the consumer decodes UTF-8.

    A single em dash in the generated header was written as cp1252 `0x97` and made
    subprocess's reader thread raise `UnicodeDecodeError` in the caller — the tool exited 0
    and the caller still failed. Prose elsewhere in this repo is free to use em dashes;
    anything this script writes to a pipe is not.
    """
    rendered = cc.render(cc.collect(_pyproject()), _PYPROJECT)
    offenders = sorted({c for c in rendered if ord(c) > 127})
    assert not offenders, f"generated constraints text contains non-ASCII {offenders}"

    source = _TOOL_PATH.read_text(encoding="utf-8")
    printed = re.findall(r"print\(\s*(?:f?\"[^\"]*\"|f?'[^']*')", source, re.MULTILINE)
    assert printed, "no print() literals found — this scan has gone stale"
    bad = sorted({c for literal in printed for c in literal if ord(c) > 127})
    assert not bad, f"print() literals contain non-ASCII {bad}; a pipe consumer may not decode them"


def test_a_package_declared_twice_with_different_bounds_is_refused(tmp_path):
    """pip permits one constraint per name; emitting two would fail at install time."""
    bad = tmp_path / "pyproject.toml"
    bad.write_text(
        "[project]\nname='x'\ndependencies=['gguf>=0.10,<1.0']\n"
        "[project.optional-dependencies]\ndev=['gguf>=0.10,<2.0']\n",
        encoding="utf-8",
    )
    result = _run_tool("--pyproject", str(bad))
    assert result.returncode == cc.EXIT_OPERATIONAL
    assert "declared twice with different bounds" in result.stderr
    assert not result.stdout, "nothing should be emitted when the input is inconsistent"


def test_a_requirement_with_extras_is_refused(tmp_path):
    bad = tmp_path / "pyproject.toml"
    bad.write_text("[project]\nname='x'\ndependencies=['gguf[cli]>=0.10,<1.0']\n", encoding="utf-8")
    result = _run_tool("--pyproject", str(bad))
    assert result.returncode == cc.EXIT_OPERATIONAL
    assert "extras" in result.stderr


def test_a_missing_pyproject_is_operational_not_a_traceback(tmp_path):
    result = _run_tool("--pyproject", str(tmp_path / "absent.toml"))
    assert result.returncode == cc.EXIT_OPERATIONAL
    assert "Traceback" not in result.stderr


def test_a_bom_does_not_defeat_the_reader(tmp_path):
    """PowerShell's `-Encoding utf8` writes a BOM and has corrupted files in this repo before."""
    bom = tmp_path / "pyproject.toml"
    bom.write_bytes(b"\xef\xbb\xbf" + b"[project]\nname='x'\ndependencies=['psutil>=5.9']\n")
    result = _run_tool("--pyproject", str(bom))
    assert result.returncode == cc.EXIT_OK
    assert "psutil>=5.9" in result.stdout


def test_it_survives_an_interpreter_without_stdlib_tomllib():
    """pyproject supports 3.10, where tomllib does not exist — and CI's 3.10 job runs this
    script before installing anything, so the import cannot be assumed.

    Blocking `tomllib` via `sys.modules[...] = None` makes `import tomllib` raise
    ImportError, reproducing 3.10 on any interpreter. The tool must then either use `tomli`
    or say so in a sentence; what it must never do is die with a traceback in a CI step
    whose whole job is to make the install reproducible.
    """
    driver = (
        "import sys, runpy;"
        "sys.modules['tomllib'] = None;"
        f"sys.argv = ['ci_constraints.py', '--pyproject', {str(_PYPROJECT)!r}];"
        f"runpy.run_path({str(_TOOL_PATH)!r}, run_name='__main__')"
    )
    result = subprocess.run([sys.executable, "-c", driver], capture_output=True, text=True, check=False)
    assert "Traceback" not in result.stderr, result.stderr
    if result.returncode == cc.EXIT_OK:
        assert "gguf>=0.10,<1.0" in result.stdout  # tomli is installed here and the fallback worked
    else:
        assert result.returncode == 2
        assert "pip install tomli" in result.stderr


def test_the_real_pyproject_generates_cleanly():
    result = _run_tool(cwd=str(_ROOT))
    assert result.returncode == cc.EXIT_OK, result.stderr
    assert "gguf>=0.10,<1.0" in result.stdout
