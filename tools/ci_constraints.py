#!/usr/bin/env python3
"""Emit a pip constraints file from pyproject.toml's declared bounds.

Baseline CI installs the complete hash-locked graph. This helper remains for
manual subset installs (`pip install pytest scipy gguf inspect-ai ...`), where
unconstrained packages bypass pyproject's bounds. Current GGUF caps and the exact
`inspect-ai==0.3.269` observed SDK pin must survive those subset installs.

Hand-copying bounds trades one drift for another. This script reads pyproject
and prints every requirement it declares, and `pip install -c` applies those
bounds to the chosen subset. A constraint on an uninstalled package is inert, so emitting all of them
is both correct and maintenance-free.

Usage:
    python tools/ci_constraints.py [--pyproject PATH] [--out PATH]

Exit codes:
    0  constraints written
    2  pyproject unreadable, or two extras declare conflicting bounds for one
       package (pip permits a single constraint per name, so this must be fixed
       in pyproject rather than papered over here)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# tomllib is stdlib only on 3.11+, and pyproject declares support down to 3.10 — where
# CI's test matrix runs this script BEFORE installing anything, so there is no pytest to
# drag `tomli` in. Fall back explicitly, and fail with a sentence rather than a traceback.
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover — 3.10 only
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        print(
            "no TOML parser: this interpreter predates tomllib (3.11+) and `tomli` is not "
            "installed. Install it first: pip install tomli",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

EXIT_OK = 0
EXIT_OPERATIONAL = 2

# Caps a dependency INHERITS through a parent that CI's unit job does not install.
#
# "Emit what pyproject declares" is not sufficient for a PARENT_BOUNDED dependency
# (tests/test_dependencies.py `_EXEMPTIONS`): pyproject deliberately declares no cap on it,
# because a parent caps it in every real install. The unit job installs such a package
# standalone, WITHOUT the parent, so nothing caps it there and pip takes the newest release
# -- a version no `pip install quantfit` can resolve. That is exactly the "combination the
# package forbids" this script exists to prevent; the forbidding just happens one link down.
#
# Found 2026-09-25: huggingface_hub 2.0.0 was released, CI's unit job installed it, and
# test_a_major_boundary_crossed_under_an_exemption_is_recorded failed on a major no user can
# reach. The chain, read from PyPI metadata that day: pyproject caps llmcompressor<0.13;
# llmcompressor 0.12.0 requires transformers>=5.9.0,<=5.10.1; transformers 5.9.0, 5.10.0 and
# 5.10.1 each require huggingface-hub>=1.5.0,<2.0 (as does 5.17.0, the latest).
#
# Hand-recorded, which is what this script otherwise refuses to do -- so it is pinned: when
# the parent IS installed, tests/test_ci_constraints.py checks the parent's own
# Requires-Dist still carries this cap, and fails if the chain moved.
INHERITED_CAPS: dict[str, tuple[str, str]] = {
    "huggingface-hub": ("<2.0", "transformers"),  # (cap, the installed parent that imposes it)
}

# PEP 508 name at the head of a requirement string, up to the first version
# specifier / extra / marker / whitespace.
_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """PEP 503 normalization, so `inspect-ai` and `inspect_ai` are one package."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    match = _NAME_RE.match(requirement)
    if match is None:
        raise ValueError(f"cannot parse a package name out of requirement {requirement!r}")
    return normalize(match.group(1))


def collect(pyproject: dict) -> dict[str, str]:
    """Map normalized package name -> the requirement string pyproject declares.

    Raises ValueError if one package is declared with two different specs; pip
    accepts only one constraint per name, and disagreeing declarations are a
    defect in pyproject regardless of what CI does with them.
    """
    project = pyproject.get("project", {})
    sources: list[tuple[str, list[str]]] = [("dependencies", list(project.get("dependencies", [])))]
    for extra, requirements in sorted(project.get("optional-dependencies", {}).items()):
        sources.append((f"optional-dependencies.{extra}", list(requirements)))

    seen: dict[str, tuple[str, str]] = {}  # name -> (requirement, declaring section)
    for section, requirements in sources:
        for requirement in requirements:
            if "[" in requirement:
                # pip: "Constraints cannot have extras". None are declared today;
                # refuse rather than emit a file pip will reject at install time.
                raise ValueError(f"{section}: constraint entries cannot carry extras: {requirement!r}")
            name = requirement_name(requirement)
            spec = requirement.strip()
            previous = seen.get(name)
            if previous is not None and previous[0] != spec:
                raise ValueError(
                    f"{name} is declared twice with different bounds: "
                    f"{previous[0]!r} in [{previous[1]}] and {spec!r} in [{section}]. "
                    "pip permits one constraint per package; reconcile them in pyproject."
                )
            seen[name] = (spec, section)

    constraints = {name: spec for name, (spec, _) in sorted(seen.items())}
    for name, (cap, _parent) in INHERITED_CAPS.items():
        if name in constraints:  # one constraint per name: fold the inherited cap into the declared spec
            constraints[name] = f"{constraints[name]},{cap}"
    return constraints


def render(constraints: dict[str, str], pyproject_path: Path) -> str:
    # ASCII only, deliberately. This text goes to stdout, whose encoding on Windows is the
    # console codepage (cp1252 here), while whatever consumes it — pytest's subprocess
    # reader, a CI log collector — decodes as UTF-8. An em dash written as cp1252 0x97 is
    # not valid UTF-8, so a single decorative character makes the caller raise
    # UnicodeDecodeError. That is exactly how this was found.
    lines = [
        "# GENERATED by tools/ci_constraints.py - do not edit.",
        f"# Source of truth: {pyproject_path.name} ([project.dependencies] + [project.optional-dependencies]).",
        "# Applied with `pip install -c` so CI cannot install a version the package forbids.",
    ]
    lines.extend(constraints.values())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pyproject", default="pyproject.toml", metavar="PATH", help="default: pyproject.toml")
    parser.add_argument("--out", default=None, metavar="PATH", help="write here instead of stdout")
    args = parser.parse_args(argv)

    path = Path(args.pyproject)
    try:
        # utf-8-sig, not utf-8: a stray BOM (PowerShell's `-Encoding utf8` writes one)
        # makes tomllib reject an otherwise valid file, and it has bitten this repo.
        pyproject = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    try:
        constraints = collect(pyproject)
    except ValueError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    if not constraints:
        print(f"{path} declares no dependencies; nothing to constrain", file=sys.stderr)
        return EXIT_OPERATIONAL

    text = render(constraints, path)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {len(constraints)} constraints to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
