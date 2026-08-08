"""`tools/ci_constraints.py` and the CI install steps it exists to bound.

The bug this file pins: `.github/workflows/ci.yml` installed the test dependency subset
with a bare `pip install pytest huggingface_hub psutil scipy gguf inspect-ai`. pyproject
caps two of those (`gguf>=0.10,<1.0`, `inspect-ai>=0.3.252,<0.4`) precisely because they
churn — and a bare install ignores the caps entirely, so CI could have been testing gguf
1.x against a package that declares it unsupported, staying green while the published
wheel broke.

Restating the caps in ci.yml would have swapped one drift for another, so CI derives them
from pyproject. That leaves two things to test, and both are here:

1. the generator faithfully reproduces what pyproject declares, and refuses the two inputs
   pip cannot accept (a package declared twice with different bounds, an entry with
   extras) rather than emitting a file that fails at install time;
2. the workflows actually use it — no `pip install` may name a capped package without
   either passing `-c` or stating the specifier inline, and a job that consumes the
   constraints file must generate it first.

Check 2 is the one that stops the original bug returning; check 1 is what makes it safe to
rely on.

Hermetic: reads `pyproject.toml` and two workflow files, runs the generator in-process.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

try:  # stdlib on 3.11+
    import tomllib
except ModuleNotFoundError:  # 3.10: pytest declares `tomli>=1` there
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parent.parent
_TOOL_PATH = _ROOT / "tools" / "ci_constraints.py"
_PYPROJECT = _ROOT / "pyproject.toml"
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_CANARY = _ROOT / ".github" / "workflows" / "canary.yml"

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
    assert emitted == _declared_requirements(), (
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
        assert re.search(r"<\s*\d", emitted[name]), (
            f"{name} is emitted as {emitted[name]!r} with no upper bound. It carried one when this "
            "tool was written; if the cap was removed on purpose, say so in pyproject and in "
            "tests/test_dependencies.py:_EXEMPTIONS rather than only here."
        )


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


# --------------------------------------------------------------------------------
# 2. The workflows use it — this is the check that stops the bug returning
# --------------------------------------------------------------------------------

_PIP_INSTALL_RE = re.compile(r"pip install (?P<args>.+)$")


def _pip_install_lines(path: Path) -> list[tuple[int, str, str]]:
    """(line number, whole line, argument tail) for every `pip install` in a workflow."""
    out = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = _PIP_INSTALL_RE.search(stripped)
        if match:
            out.append((number, stripped, match.group("args")))
    return out


def _named_packages(args: str) -> list[str]:
    """Bare package names in a pip argument tail — no options, paths, globs or inline specs."""
    names = []
    for token in args.split():
        if token.startswith("-") or "/" in token or "*" in token or token in {"pip", "."}:
            continue
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", token):
            names.append(cc.normalize(token))
    return names


def test_no_workflow_installs_a_capped_package_without_applying_the_cap():
    capped = _capped_packages()
    assert capped, "pyproject caps nothing, so this check has no subject — the premise is stale"

    offenders = []
    checked = 0
    for path in (_CI, _CANARY):
        for number, line, args in _pip_install_lines(path):
            named = [n for n in _named_packages(args) if n in capped]
            if not named:
                continue
            checked += 1
            # Either the constraints file is applied, or the specifier is stated inline
            # (which tests/test_dependencies.py then verifies against pyproject).
            if "-c " not in args and "--constraint" not in args:
                offenders.append(
                    f"{path.name}:{number} installs capped {named} with no constraint: {line!r}. "
                    f"Add `-c {_CONSTRAINTS_FILE}` (generated by tools/ci_constraints.py) so CI cannot "
                    "resolve a version pyproject forbids."
                )
    assert checked, (
        "no workflow install names a capped package any more — either the caps moved or this "
        "scan stopped matching. Re-point it rather than deleting it."
    )
    assert not offenders, offenders


def test_every_job_consuming_the_constraints_file_generates_it_first():
    text = _CI.read_text(encoding="utf-8")
    # Jobs are the top-level keys under `jobs:`; split on the two-space job headers.
    job_blocks = re.split(r"\n  (?=[a-z][a-z0-9-]*:\n)", text)
    problems = []
    consumers = 0
    for block in job_blocks:
        uses = f"-c {_CONSTRAINTS_FILE}" in block
        if not uses:
            continue
        consumers += 1
        generates = re.search(rf"ci_constraints\.py[^\n]*--out {re.escape(_CONSTRAINTS_FILE)}", block)
        name = block.strip().splitlines()[0].strip()
        if not generates:
            problems.append(f"job {name!r} passes -c {_CONSTRAINTS_FILE} but never generates it")
        elif block.index(f"-c {_CONSTRAINTS_FILE}") < generates.start():
            problems.append(f"job {name!r} consumes {_CONSTRAINTS_FILE} before the step that writes it")
    assert consumers >= 2, (
        f"expected the test and lint jobs to both apply {_CONSTRAINTS_FILE}; found {consumers} consumer job(s)"
    )
    assert not problems, problems


def test_the_generator_is_linted_like_the_rest_of_tools():
    """`tools/` is in ruff's target list, so a new script there is covered rather than exempt."""
    lint = re.search(r"ruff check ([^\n]+)", _CI.read_text(encoding="utf-8"))
    assert lint, "ci.yml no longer runs `ruff check`"
    assert "tools" in lint.group(1).split(), f"ruff check targets {lint.group(1)!r}, which excludes tools/"
