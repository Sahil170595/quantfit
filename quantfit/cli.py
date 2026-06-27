"""quantfit CLI — `check`, `list`, `quantize`."""

from __future__ import annotations

import argparse
import sys

from quantfit.registry import METHODS


def _force_utf8_stdio() -> None:
    # llm-compressor / gptqmodel loggers emit unicode; a Windows cp1252 console
    # otherwise crashes mid-run with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quantfit", description="Quantize an LLM if it fits your GPU.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="will this model fit your GPU?")
    pc.add_argument("--model", required=True, help="HF model id")

    sub.add_parser("list", help="list supported methods + schemes")

    pv = sub.add_parser("verify", help="smoke-load a quantized artifact + generate")
    pv.add_argument("--model", required=True, help="path to a quantized output dir or .gguf")

    pvs = sub.add_parser("verify-safety", help="refusal preservation: fp16 baseline vs quantized")
    pvs.add_argument("--fp16", required=True, help="HF id of the fp16 baseline")
    pvs.add_argument("--quant", required=True, help="path to the quantized artifact")
    pvs.add_argument("--max-new-tokens", type=int, default=64)

    pq = sub.add_parser("quantize", help="quantize a model")
    pq.add_argument("--model", required=True, help="HF model id (the FP16 base)")
    pq.add_argument("--method", required=True, choices=tuple(METHODS))
    pq.add_argument("--scheme", default=None, help="override the method's default scheme")
    pq.add_argument("--out", required=True, help="output directory")
    pq.add_argument("--push", default=None, help="HF repo id to upload the result to")
    pq.add_argument("--private", action="store_true", help="push as a private repo")
    pq.add_argument("--offload", action="store_true", help="quantize on CPU (fits any size, slower)")
    pq.add_argument("--no-check", action="store_true", help="skip the GPU pre-flight")
    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args(argv)

    if args.cmd == "check":
        from quantfit.fit import plan

        cap = plan(args.model)
        print(cap.reason())
        return 0 if cap.fits else 2

    if args.cmd == "list":
        from quantfit.registry import catalog

        print(catalog())
        return 0

    if args.cmd == "verify":
        from quantfit.verify import verify

        ok, msg = verify(args.model)
        print(("PASS: " if ok else "FAIL: ") + msg)
        return 0 if ok else 2

    if args.cmd == "verify-safety":
        from quantfit.safety.verify import verify_safety

        tax = verify_safety(args.fp16, args.quant, max_new_tokens=args.max_new_tokens)
        print(tax.summary())  # aggregates only — never echoes raw probe prompts/completions
        return 0 if tax.clean else 2

    if args.cmd == "quantize":
        from quantfit.quantize import CannotQuantize, push, quantize
        from quantfit.registry import UnsupportedCombo

        try:
            out = quantize(
                args.model,
                args.method,
                args.out,
                scheme=args.scheme,
                run_check=not args.no_check,
                offload=args.offload,
            )
        except (CannotQuantize, UnsupportedCombo) as exc:
            print(exc)
            return 2
        print(f"quantized -> {out}")
        if args.push:
            print(f"pushed -> {push(str(out), args.push, private=args.private)}")
        return 0

    return 1  # unreachable: subparser is required


if __name__ == "__main__":
    raise SystemExit(main())
