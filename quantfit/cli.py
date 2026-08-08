"""quantfit CLI — check / list / plan / probe / quantize / verify / verify-safety / screen / emit."""

from __future__ import annotations

import argparse
import sys

from quantfit.gate import TIERS as GATE_TIERS  # tier NAMES only — no torch, no heavy import
from quantfit.registry import METHODS


def _force_utf8_stdio() -> None:
    # llm-compressor loggers emit unicode; a Windows cp1252 console
    # otherwise crashes mid-run with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="quantfit",
        description="Quantize an LLM, check it fits your GPU, and verify it still refuses what it should.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # Shared --token for the commands that hit the Hub (gated / private models).
    tok = argparse.ArgumentParser(add_help=False)
    tok.add_argument("--token", default=None, help="HF token for gated/private models (else uses the HF_TOKEN env)")

    pc = sub.add_parser(
        "check",
        parents=[tok],
        help="will this model fit your GPU? (exit 0 = fits, 3 = won't fit, 2 = operational error)",
    )
    pc.add_argument("--model", required=True, help="HF model id")

    sub.add_parser("list", help="list supported methods + schemes")

    pp = sub.add_parser("plan", parents=[tok], help="show the config quantfit would pick for your GPU (no quantize)")
    pp.add_argument("--model", required=True, help="HF model id")
    pp.add_argument("--prefer", default="quality", choices=("quality", "speed", "size"))

    ppr = sub.add_parser("probe", parents=[tok], help="measure how much a model degrades at each bit-width (RTN-KL)")
    ppr.add_argument("--model", required=True, help="HF model id")
    ppr.add_argument("--bits", type=int, nargs="+", default=[4, 8], help="bit-widths to probe")

    pv = sub.add_parser(
        "verify",
        help="smoke-load a quantized artifact + generate (GGUF: structural magic check only) "
        "(exit 0 = pass, 3 = fail, 2 = operational error)",
    )
    pv.add_argument("--model", required=True, help="path to a quantized output dir or .gguf")

    pvs = sub.add_parser(
        "verify-safety",
        parents=[tok],
        help="refusal preservation: unquantized baseline vs quantized "
        "(exit 0 = no regression detected, 3 = regression, 4 = axis unmeasurable, 2 = operational error)",
    )
    pvs.add_argument(
        "--baseline",
        "--fp16",  # legacy alias from 0.1-0.3; the baseline loads at its NATIVE dtype (often bf16)
        dest="baseline",
        required=True,
        help="the unquantized baseline: an HF id (loaded at its native dtype — often bf16), or for "
        "GGUF pairs an F16/BF16/F32 GGUF (*.gguf path or hf:<org>/<repo>/<file>.gguf) run under "
        "the identical pinned llama.cpp binary as --quant",
    )
    pvs.add_argument(
        "--quant",
        required=True,
        help="the quantized artifact: an output dir, or a *.gguf / hf:<org>/<repo>/<file>.gguf ref "
        "(GGUF quant requires a GGUF baseline — both arms one binary, CPU)",
    )
    pvs.add_argument(
        "--max-new-tokens",
        type=int,
        default=64,
        help="completion length generated per probe and judged for refusal (default 64)",
    )
    pvs.add_argument(
        "--report",
        default=None,
        metavar="PATH",
        help="also write the run as an auditable JSON report (schema v2: revision pins, "
        "resolved precisions, per-arm engine provenance, env fingerprint, per-arm runtimes)",
    )
    pvs.add_argument(
        "--capture",
        default=None,
        metavar="PATH",
        help="ALSO write every completion to a local JSONL for judge calibration (may contain "
        "harmful model output; never commit, redistribute, or attach to a report — see "
        "docs/data-handling-completions.md; use the *.capture.jsonl suffix)",
    )

    ps = sub.add_parser(
        "screen",
        parents=[tok],
        help="run verify-safety over a target manifest and aggregate per-stratum, per-axis prevalence bounds "
        "(exit 0 = no regression flagged, 3 = regression flagged, 4 = an axis went unmeasured, 2 = operational error)",
    )
    ps.add_argument("--targets", required=True, metavar="PATH", help="target manifest JSON (schema v1)")
    ps.add_argument(
        "--out", required=True, metavar="DIR", help="output dir: one drift report per target + screen-summary.json"
    )
    ps.add_argument(
        "--max-new-tokens",
        type=int,
        default=64,
        help="completion length generated per probe and judged for refusal (default 64)",
    )

    pe = sub.add_parser(
        "emit",
        help="render an artifact from a drift report (exit 0 = emitted, 2 = unreadable/wrong-schema report)",
    )
    pe.add_argument("what", choices=("model-card",), help="what to emit")
    pe.add_argument("--report", required=True, metavar="PATH", help="a schema-v2 drift report written by --report")

    pca = sub.add_parser(
        "calibrate",
        help="judge-calibration machinery (ROADMAP 0.6; labeling itself starts only on the 0.5 GO): "
        "build a blinded labeling sheet from a capture, or ingest filled labels into a calibration report "
        "(exit 0 = done, 2 = operational error)",
    )
    csub = pca.add_subparsers(dest="calibrate_cmd", required=True)
    pcs = csub.add_parser("sheet", help="capture JSONL -> blinded labeling sheet CSV + unblinding key JSON")
    pcs.add_argument("--capture", required=True, metavar="PATH", help="a *.capture.jsonl written by --capture")
    pcs.add_argument("--sheet", required=True, metavar="PATH", help="blinded sheet to write (*.labels.csv)")
    pcs.add_argument("--key", required=True, metavar="PATH", help="unblinding key to write (*.labelkey.json)")
    pci = csub.add_parser("ingest", help="filled sheet + key -> per-arm judge-error calibration report")
    pci.add_argument("--sheet", required=True, metavar="PATH", help="the filled labeling sheet")
    pci.add_argument("--key", required=True, metavar="PATH", help="the key written next to it")
    pci.add_argument("--out", required=True, metavar="PATH", help="calibration report JSON to write (counts only)")

    pg = sub.add_parser(
        "gate",
        parents=[tok],
        help="pre-release gate: does this quant hold a declared refusal-robustness threshold? "
        "(exit 0 = pass, 3 = fail, 4 = gated axis unmeasurable, 5 = threshold finer than the "
        "instrument's resolution, 2 = operational error)",
    )
    pg.add_argument("--baseline", "--fp16", dest="baseline", required=True, help="the unquantized baseline arm")
    pg.add_argument("--quant", required=True, help="the quantized artifact to gate")
    gthr = pg.add_mutually_exclusive_group(required=True)
    gthr.add_argument(
        "--threshold",
        type=float,
        metavar="PP",
        help="declared dangerous-axis flip-rate threshold in PERCENTAGE POINTS (e.g. 30 = 30pp)",
    )
    gthr.add_argument("--tier", choices=tuple(GATE_TIERS), help="a named tier instead of a raw threshold")
    pg.add_argument(
        "--eps-upper",
        type=float,
        default=None,
        metavar="RATE",
        help="per-arm upper bound on BOTH directional judge-error rates (a calibration report's "
        "mde_epsilon_upper). Without it the gate prints a perfect-judge FLOOR, not a resolution",
    )
    pg.add_argument(
        "--eps-source",
        default=None,
        metavar="STR",
        help="where --eps-upper came from (required with it: an unsourced epsilon is not evidence)",
    )
    pg.add_argument("--max-new-tokens", type=int, default=64, help="completion length per probe (default 64)")
    pg.add_argument("--report", default=None, metavar="PATH", help="also write the schema-v2 drift report")
    pg.add_argument("--out", default=None, metavar="PATH", help="write the gate decision artifact JSON")

    pr = sub.add_parser(
        "reproduce",
        help="is this report a reproduction of that one? applies the QSR v0 cross-hardware tolerance "
        "(exit 0 = reproduced, 3 = breach or not-met, 4 = nothing was compared, 2 = operational error)",
    )
    pr.add_argument("--reference", required=True, metavar="PATH", help="the reference schema-v2 drift report")
    pr.add_argument("--candidate", required=True, metavar="PATH", help="the report claiming to reproduce it")
    pr.add_argument("--out", default=None, metavar="PATH", help="write the comparison record JSON")
    pr.add_argument(
        "--t0-reference",
        nargs="+",
        default=None,
        metavar="REPORT",
        help="within-hardware replicate reports for the REFERENCE side (3 per the protocol). T0 is not "
        "computable from two reports, so without this the outcome can never be the gate pass",
    )
    pr.add_argument(
        "--t0-candidate",
        nargs="+",
        default=None,
        metavar="REPORT",
        help="within-hardware replicate reports for the CANDIDATE side",
    )

    pau = sub.add_parser(
        "audit",
        help="docs=code parity: do the docs still describe the code? "
        "(exit 0 = clean, 3 = drift found, 2 = operational error)",
    )
    pau.add_argument("--root", default=None, metavar="DIR", help="repo root (default: the one containing quantfit)")
    pau.add_argument("--json", default=None, metavar="PATH", help="also write the findings as JSON")

    pq = sub.add_parser("quantize", parents=[tok], help="quantize a model")
    pq.add_argument("--model", required=True, help="HF model id (the full-precision base)")
    pq.add_argument("--method", required=True, choices=tuple(METHODS))
    pq.add_argument("--scheme", default=None, help="override the method's default scheme")
    pq.add_argument("--out", required=True, help="output directory")
    pq.add_argument("--push", default=None, help="HF repo id to upload the result to")
    pq.add_argument("--private", action="store_true", help="push as a private repo")
    pq.add_argument("--no-check", action="store_true", help="skip the GPU pre-flight")
    return p


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "check":
        from quantfit.fit import capacity_plan

        cap = capacity_plan(args.model, token=args.token)
        print(cap.reason())
        return 0 if cap.fits else 3  # 3 = the doesn't-fit verdict; 2 stays operational-error

    if args.cmd == "list":
        from quantfit.registry import catalog

        print(catalog())
        return 0

    if args.cmd == "plan":
        from quantfit.engines.base import Budget
        from quantfit.engines.compressed_tensors import CompressedTensorsEngine
        from quantfit.engines.gguf import GgufEngine
        from quantfit.policy.route import route
        from quantfit.policy.target import detect_target

        target = detect_target()
        routed = route(args.model, target, Budget(prefer=args.prefer), [CompressedTensorsEngine(), GgufEngine()])
        print(f"target: {target.device}/{target.gpu_arch or '-'} serve={target.serve}")
        print(f"pick:   {routed.config.method} {routed.config.scheme}  [{routed.config.engine}]")
        print(f"why:    {routed.rationale}")
        return 0

    if args.cmd == "probe":
        from quantfit.policy.probe import probe_sensitivity

        print("sensitivity — mean per-token RTN-KL(fp16 || quant); higher = more degradation:")
        for bits in args.bits:
            r = probe_sensitivity(args.model, bits=bits, token=args.token)
            print(f"  {bits}-bit: KL {r.mean_kl:.3f}  (n={r.n_samples})")
        print("note: RTN is the worst case — LOW KL = safe bit-width; HIGH KL can over-escalate")
        print("      (calibrated AWQ/GPTQ may still be fine). Read it as sensitivity, not a verdict.")
        return 0

    if args.cmd == "verify":
        from quantfit.verify import verify

        ok, msg = verify(args.model)
        print(("PASS: " if ok else "FAIL: ") + msg)
        return 0 if ok else 3  # 3 = the smoke-test verdict; 2 stays operational-error

    if args.cmd == "verify-safety":
        from quantfit.safety.verify import verify_safety

        drift = verify_safety(
            args.baseline,
            args.quant,
            token=args.token,
            max_new_tokens=args.max_new_tokens,
            report_path=args.report,
            capture_path=args.capture,
        )
        print(drift.summary())  # aggregates only — never echoes raw probe prompts/completions
        if args.report:
            print(f"report -> {args.report}")
        # Exit codes are the CI contract; they must not collide with 2 (operational
        # failure, from main's handler) or an unmeasured run would read as a verdict.
        if drift.regression_detected:
            return 3
        if drift.unmeasurable_axes:
            return 4  # zero at-risk pairs on an axis: nothing was measured, not a pass
        return 0

    if args.cmd == "screen":
        from quantfit.screen import STATUS_REGRESSION, STATUS_UNMEASURABLE, run_screen

        summary = run_screen(args.targets, args.out, token=args.token, max_new_tokens=args.max_new_tokens)
        for stratum, agg in sorted(summary["by_stratum"].items()):
            print(f"{stratum}: {agg['n_completed']}/{agg['n_targets']} completed, {agg['n_operational_errors']} errors")
            for axis in ("refusal_robustness", "over_refusal"):
                a = agg[axis]
                lo, hi = a["prevalence_bound_wilson95"]
                label = f" [{a['conditionality']}]" if a["conditionality"] else ""
                print(
                    f"  {axis}: {a['n_regressed']}/{a['n_measured']} flagged "
                    f"(95% CI {lo * 100:.1f}-{hi * 100:.1f}%){label}"
                )
        print(f"summary -> {args.out}/screen-summary.json")
        statuses = {row["status"] for row in summary["rows"]}
        axes = [a for agg in summary["by_stratum"].values() for a in (agg["refusal_robustness"], agg["over_refusal"])]
        # Same contract as verify-safety: a flagged regression outranks unmeasured.
        if STATUS_REGRESSION in statuses:
            return 3
        if STATUS_UNMEASURABLE in statuses or any(a["n_measured"] == 0 for a in axes):
            return 4  # an axis nothing was measured on is not a clean screen
        return 0

    if args.cmd == "emit":
        from quantfit.modelcard import model_card_fragment

        print(model_card_fragment(args.report), end="")  # fragment carries its own trailing newline
        return 0

    if args.cmd == "gate":
        from quantfit.gate import run_gate

        # --threshold is percentage points at the CLI boundary; run_gate takes a rate.
        # The conversion lives here so the machinery has one unit and the operator has
        # the one they think in (a silent 100x is the failure mode this splits apart).
        threshold = args.threshold / 100 if args.threshold is not None else None
        decision = run_gate(
            args.baseline,
            args.quant,
            threshold=threshold,
            tier=args.tier,
            eps_upper=args.eps_upper,
            eps_source=args.eps_source,
            token=args.token,
            max_new_tokens=args.max_new_tokens,
            report_path=args.report,
            out_path=args.out,
        )
        print(decision["headline"])
        if args.out:
            print(f"gate decision -> {args.out}")
        return decision["exit_code"]

    if args.cmd == "calibrate":
        if args.calibrate_cmd == "sheet":
            from quantfit.safety.calibrate import build_labeling_sheet

            sheet, key = build_labeling_sheet(args.capture, args.sheet, args.key)
            print(f"blinded sheet -> {sheet}")
            print(f"unblinding key -> {key} (labeler never sees this file)")
            return 0
        from quantfit.safety.calibrate import ingest_labels

        report = ingest_labels(args.sheet, args.key, args.out)
        for arm in ("baseline", "quantized"):
            block = report[arm]
            eps = block["epsilon"]
            print(
                f"{arm}: n={block['n']} judge_errors={block['judge_errors']} "
                f"epsilon={'unmeasured' if eps is None else f'{eps:.4f}'}"
            )
        print(f"calibration report -> {args.out} (counts only, no completion text)")
        return 0

    if args.cmd == "reproduce":
        from quantfit.reproduce import compare, within_hardware_identical

        # Replicate sets are turned into T0 results HERE rather than inside compare():
        # T0 is a within-hardware property of three runs, and keeping the conversion at
        # the boundary is what lets the artifact record which files supplied it.
        t0_ref = within_hardware_identical(args.t0_reference) if args.t0_reference else None
        t0_cand = within_hardware_identical(args.t0_candidate) if args.t0_candidate else None
        decision = compare(args.reference, args.candidate, args.out, t0_reference=t0_ref, t0_candidate=t0_cand)
        print(decision["headline"])
        if args.out:
            print(f"comparison record -> {args.out}")
        return decision["exit_code"]

    if args.cmd == "audit":
        from quantfit.audit import audit, summarize

        result = audit(args.root)
        print(summarize(result))
        if args.json:
            import json
            from pathlib import Path

            Path(args.json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"audit findings -> {args.json}")
        return result["exit_code"]

    if args.cmd == "quantize":
        from quantfit.quantize import CannotQuantize, push, quantize
        from quantfit.registry import UnsupportedCombo

        try:
            out = quantize(
                args.model,
                args.method,
                args.out,
                scheme=args.scheme,
                token=args.token,
                run_check=not args.no_check,
            )
        except (CannotQuantize, UnsupportedCombo) as exc:
            print(exc)
            return 2
        print(f"quantized -> {out}")
        if args.push:
            print(f"pushed -> {push(str(out), args.push, token=args.token, private=args.private)}")
        return 0

    return 1  # unreachable: subparser is required


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (RuntimeError, OSError) as exc:
        # Operational failures (no GPU, gated/missing model, network, disk, short
        # calibration/probe datasets — quantfit raises its own as RuntimeError) ->
        # a clean message + exit 2, not a traceback. Programming errors, including
        # ValueError from anywhere in the torch/transformers stack, surface raw.
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
