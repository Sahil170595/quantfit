"""Offline original-byte screen-bundle creation and strict verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantfit.reproduce import _canonical_receiving_path
from quantfit.screen_bundle_inputs import (
    ScreenBundleError,
    _capture_bundle,
    _capture_source,
    _require,
    _verify_held,
)
from quantfit.screen_bundle_publication import _publish


def create_screen_bundle(manifest_path: str, reports_dir: str, out_dir: str) -> dict[str, Any]:
    """Hold and validate exact originals; create a new directory with readiness manifest last."""
    try:
        target = Path(_canonical_receiving_path(out_dir))
        _require(target.parent.is_dir() and not target.exists(), "invalid_destination")
        source_root = Path(_canonical_receiving_path(reports_dir))
        _require(not target.is_relative_to(source_root), "invalid_destination")
        held = _capture_source(manifest_path, reports_dir)
        result = _verify_held(held)
        files = (
            ("targets.json", held.targets),
            *((f"reports/{name}", raw) for name, raw in held.members),
            ("manifest.json", held.outer),
        )
        _publish(target, files)
        return result
    except ScreenBundleError:
        raise
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise ScreenBundleError("invalid_screen_bundle_input") from None


def verify_screen_bundle(bundle_dir: str) -> dict[str, Any]:
    """Capture once and re-receive the exact closed transport without following report references."""
    try:
        return _verify_held(_capture_bundle(bundle_dir))
    except ScreenBundleError:
        raise
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise ScreenBundleError("invalid_screen_bundle_input") from None
