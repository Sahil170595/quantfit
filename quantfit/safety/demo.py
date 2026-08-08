"""A real verdict in under two minutes, from fixtures, marked so it cannot pass for one.

The adoption problem this solves: of the CLI's commands, only `list` and `plan` did
anything without a GPU, a network and two model artifacts. Everything that demonstrates
why quantfit exists needed a multi-gigabyte download first, so most evaluations ended
before the first verdict — while the tools people already have installed print something
within a minute.

What this is: the **real** tabulation. `demo_drift()` builds `Probe` objects and refusal
flags and hands them to `safety.verify._tabulate`, the same function a live run uses, so
the Wilson bounds, the at-risk denominators, the two-axis split and the verdict precedence
are all genuinely computed. Nothing here re-implements the statistics; a second copy would
be the divergence channel the spec exists to prevent.

What this is not, and why that is enforced rather than mentioned:

- **The probe prompts are placeholders**, not the curated corpus. Shipping real
  expected-unsafe prompts in the package to make a demo prettier would put harmful text in
  every wheel, for a feature whose entire job is convenience.
- **The refusal flags are fixtures**, not judgements. No model ran, so nothing was
  measured about any model.
- Every surface says so: `DEMONSTRATION` leads the verdict line, `demo` is `true` in the
  JSON payload, and `--demo` refuses `--report` outright — an artifact indistinguishable
  from a real report is the one thing this must never produce.

The fixture is deliberately a *regression*: a no-detection demo would teach the reader the
shape of the output but not the shape of a finding, and the finding is the point.
"""

from __future__ import annotations

from quantfit.safety.verify import EXPECTED_SAFE, EXPECTED_UNSAFE, Probe, SafetyDrift, _tabulate

# Marker text. Load-bearing: it is asserted by the tests and read by anyone skimming output.
DEMO_VERDICT_PREFIX = "DEMONSTRATION — fixtures, not a measurement"

DEMO_NOTE = (
    "No model was loaded and nothing was judged. The probe prompts are placeholders and the "
    "refusal flags are fixtures; only the statistics are real. Run `quantfit verify-safety "
    "--baseline <id> --quant <path>` for a measurement."
)

# (zone, expected, baseline_refused, quant_refused). Placeholder prompts only — the real
# corpus is loaded from a pinned dataset revision at run time and is not shipped here.
_FIXTURE: tuple[tuple[str, str, bool, bool], ...] = (
    # refusal-robustness axis: baseline refuses; two flips to compliance is the finding.
    ("clear_unsafe", EXPECTED_UNSAFE, True, True),
    ("clear_unsafe", EXPECTED_UNSAFE, True, True),
    ("clear_unsafe", EXPECTED_UNSAFE, True, False),  # dangerous flip
    ("clear_unsafe", EXPECTED_UNSAFE, True, True),
    ("borderline", EXPECTED_UNSAFE, True, False),  # dangerous flip
    ("borderline", EXPECTED_UNSAFE, True, True),
    ("borderline", EXPECTED_UNSAFE, False, False),  # baseline complied: not at risk
    ("clear_unsafe", EXPECTED_UNSAFE, True, True),
    # over-refusal axis: baseline complies; one flip to refusal.
    ("clear_safe", EXPECTED_SAFE, False, False),
    ("clear_safe", EXPECTED_SAFE, False, True),  # over-refusal flip
    ("clear_safe", EXPECTED_SAFE, False, False),
    ("clear_safe", EXPECTED_SAFE, True, True),  # baseline refused: not at risk
)


def demo_probes() -> list[Probe]:
    """Placeholder probes carrying the zone/expected structure the tabulation needs."""
    return [
        Probe(prompt=f"<demo placeholder probe {i + 1}: not a real prompt>", zone=zone, expected=expected)
        for i, (zone, expected, _, _) in enumerate(_FIXTURE)
    ]


def demo_drift() -> SafetyDrift:
    """Run the real tabulation over the fixture and return a real `SafetyDrift`."""
    probes = demo_probes()
    baseline = [b for _, _, b, _ in _FIXTURE]
    quant = [q for _, _, _, q in _FIXTURE]
    return _tabulate(probes, baseline, quant)


def demo_summary(drift: SafetyDrift) -> str:
    """The genuine summary, with the demonstration banner wrapped around it."""
    return f"{DEMO_VERDICT_PREFIX}\n{drift.summary()}\n  {DEMO_NOTE}"
