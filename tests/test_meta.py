"""Release hygiene: version parity + terminology purge (the 0.3 gate, as tests).

0.1.0 shipped to PyPI with `__init__.__version__` trailing pyproject (0.1.0 vs
0.2.0) — a skew nothing caught. These tests make both halves of that failure
impossible to repeat silently.
"""

import re
from pathlib import Path

import quantfit

_ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject():
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, flags=re.MULTILINE)
    assert match, "pyproject.toml has no version line"
    assert quantfit.__version__ == match.group(1)


def test_no_safety_tax_on_shipped_surfaces():
    # "safety tax" collides with the literature's alignment-tax usage (capability
    # paid FOR safety) — quantfit measures the opposite and says "safety drift".
    # Shipped surfaces = code, README, package metadata. CHANGELOG is history and
    # exempt; ROADMAP discusses the rename and is exempt.
    surfaces = [_ROOT / "README.md", _ROOT / "pyproject.toml", *sorted((_ROOT / "quantfit").rglob("*.py"))]
    pattern = re.compile(r"safety[ -]?tax", flags=re.IGNORECASE)
    offenders = [str(f) for f in surfaces if pattern.search(f.read_text(encoding="utf-8"))]
    assert not offenders, f"'safety tax' still on shipped surfaces: {offenders}"
