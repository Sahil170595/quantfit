"""quantfit CLI — check / list / plan / probe / quantize / verify / verify-safety."""

from __future__ import annotations

import argparse
import sys

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
