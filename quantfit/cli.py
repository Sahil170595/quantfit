"""quantfit CLI — `check` and `quantize`."""
from __future__ import annotations

import argparse
import sys


def _force_utf8_stdio() -> None:
    # llm-compressor / gptqmodel loggers emit unicode; a Windows cp1252 console
    # otherwise crashes mid-run with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="quantfit", description="Quantize an LLM if it fits your GPU."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="will this model fit your GPU?")
    pc.add_argument("--model", required=True, help="HF model id")

    pq = sub.add_parser("quantize", help="quantize a model (AWQ/GPTQ)")
    pq.add_argument("--model", required=True, help="HF model id (the FP16 base)")
    pq.add_argument("--method", required=True, choices=("awq", "gptq"))
    pq.add_argument("--out", required=True, help="output directory")
    pq.add_argument("--push", default=None, help="HF repo id to upload the result to")
    pq.add_argument("--private", action="store_true", help="push as a private repo")
    pq.add_argument("--no-check", action="store_true", help="skip the GPU pre-flight")
    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args(argv)

    if args.cmd == "check":
        from quantfit.gpufit import check_fit

        report = check_fit(args.model)
        print(report.reason())
        return 0 if report.fits else 2

    if args.cmd == "quantize":
        from quantfit.quantize import CannotQuantize, push, quantize

        try:
            out = quantize(args.model, args.method, args.out, run_check=not args.no_check)
        except CannotQuantize as exc:
            print(exc)
            return 2
        print(f"quantized -> {out}")
        if args.push:
            print(f"pushed -> {push(str(out), args.push, private=args.private)}")
        return 0

    return 1  # unreachable: subparser is required


if __name__ == "__main__":
    raise SystemExit(main())
