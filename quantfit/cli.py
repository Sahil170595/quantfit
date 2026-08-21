"""quantfit CLI — check / list / plan / probe / quantize / verify / verify-safety / screen / emit."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from quantfit import __version__  # plain module-level string; the heavy surface stays lazy
from quantfit.gate import TIERS as GATE_TIERS  # tier NAMES only — no torch, no heavy import
from quantfit.registry import METHODS

# The envelope every `--json` run prints. Versioned from the start: the whole point of a
# machine-readable surface is that a consumer can tell when its assumptions expired, and a
# bare top-level array — which is what the sibling planner emits — leaves nowhere to say so.
CLI_JSON_SCHEMA_VERSION = 1


def _emit(args: argparse.Namespace, command: str, code: int, result: dict, human: Callable[[], None]) -> int:
    """Print one JSON document, or the prose rendering, and return the exit code.

    Under `--json`, stdout carries exactly one document and nothing else. Anything that
    would otherwise be a human notice ("report -> path") is either a field in `result` or
    goes to stderr, because a caller that has to strip lines before parsing does not have a
    contract. The exit code is unchanged either way — it stays the CI contract, and the
    document merely carries the numbers the exit code cannot.
    """
    if not getattr(args, "json", False):
        human()
        return code
    document = {
        "schema_version": CLI_JSON_SCHEMA_VERSION,
        "tool": {"name": "quantfit", "version": __version__},
        "command": command,
        "exit_code": code,
        "result": result,
    }
    json.dump(document, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return code


def _emit_error(args: argparse.Namespace, message: str, kind: str) -> int:
    """The operational-failure path, in whichever rendering was asked for.

    A caller that passed `--json` gets JSON even when the run failed; otherwise the very
    case it most needs to parse — the failure — is the one case it cannot.
    """
    if not getattr(args, "json", False):
        print(f"error: {message}")
        return 2
    document = {
        "schema_version": CLI_JSON_SCHEMA_VERSION,
        "tool": {"name": "quantfit", "version": __version__},
        "command": getattr(args, "cmd", None),
        "exit_code": 2,
        "result": None,
        "error": {"kind": kind, "message": message},
    }
    json.dump(document, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 2


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
    # `version` exits during parsing, so it answers even though the subcommand below is
    # required — `quantfit --version` used to exit 2 with a usage dump, which made the
    # first thing any caller runs to confirm an install look like a broken install.
    p.add_argument("--version", "-V", action="version", version=f"quantfit {__version__}")
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

    # No --token: `plan` reads the local device and the frozen spec only — detect_target(),
    # Engine.feasible(target) and route() never reach the Hub — so a token flag here would
    # promise gated-model support the command cannot have. It was accepted and never read.
    pp = sub.add_parser("plan", help="show the config quantfit would pick for your GPU (no quantize)")
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
        # Not argparse-required, because `--demo` is a valid invocation without it. The pair
        # is still mandatory for a real run; that check moved into the dispatch so its
        # failure is a quantfit RuntimeError -> exit 2 with a clean message, which is also
        # the only form `--json` can carry. An argparse usage dump is not parseable.
        default=None,
        help="the unquantized baseline: an HF id (loaded at its native dtype — often bf16), or for "
        "GGUF pairs an F16/BF16/F32 GGUF (*.gguf path or hf:<org>/<repo>/<file>.gguf) run under "
        "the identical pinned llama.cpp binary as --quant",
    )
    pvs.add_argument(
        "--quant",
        default=None,  # see --baseline: mandatory for a real run, checked in the dispatch
        help="the quantized artifact: an output dir, or a *.gguf / hf:<org>/<repo>/<file>.gguf ref "
        "(GGUF quant requires a GGUF baseline — both arms one binary, CPU)",
    )
    pvs.add_argument(
        "--demo",
        action="store_true",
        help="run the real tabulation over bundled FIXTURES and print the report shape — no model, "
        "no network, no weights, nothing measured. Refuses --report; always exits 0",
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
        "--junit",
        default=None,
        metavar="PATH",
        help="also write the verdict as JUnit XML, so it renders as a test result in any CI "
        "system (one case per axis; an unmeasurable axis is skipped, never passed)",
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
        "--junit",
        default=None,
        metavar="PATH",
        help="also write the screen as JUnit XML — one test case per target",
    )
    ps.add_argument(
        "--max-new-tokens",
        type=int,
        default=64,
        help="completion length generated per probe and judged for refusal (default 64)",
    )
    ps.add_argument(
        "--resume",
        action="store_true",
        help="skip targets whose report already exists in --out, rebuilding their rows from disk. "
        "A screen over a big manifest is hours long and a machine that cannot hold every pair at "
        "once must run it in pieces; without this, an interruption costs every completed target",
    )
    ps.add_argument(
        "--attempts",
        type=int,
        default=1,
        metavar="N",
        help="retry a target up to N times before recording it as an operational error (default 1, "
        "i.e. no retry). The absorbed failure class is mostly transient - a Hub blip or a closed "
        "connection - and without a retry one becomes a permanent hole in the prevalence bound",
    )
    ps.add_argument(
        "--capture",
        default=None,
        metavar="DIR",
        help="ALSO write every completion to DIR/<target>.capture.jsonl, one file per target, so a "
        "flagged flip can be adjudicated against the bytes the judge scored (QSR v0 requires "
        "human verification before a flip counts). May contain harmful model output; never "
        "commit or redistribute - see docs/data-handling-completions.md",
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
    pg.add_argument(
        "--junit",
        default=None,
        metavar="PATH",
        help="also write the gate verdict as JUnit XML: resolution, gated axis and ungated "
        "axis as separate cases, so exit 5 fails as a refusal rather than as a breached threshold",
    )

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
    # `--json-out PATH`, not `--json PATH`: `--json` is the tool-wide boolean below, and one
    # flag name may not mean "write a file here" on one command and "print to stdout" on the
    # other twelve. Renamed before `audit` had a released user; it first ships in 0.6.0.
    pau.add_argument("--json-out", default=None, metavar="PATH", help="also write the findings as a JSON file")

    pq = sub.add_parser("quantize", parents=[tok], help="quantize a model")
    pq.add_argument("--model", required=True, help="HF model id (the full-precision base)")
    pq.add_argument("--method", required=True, choices=tuple(METHODS))
    pq.add_argument("--scheme", default=None, help="override the method's default scheme")
    pq.add_argument("--out", required=True, help="output directory")
    pq.add_argument("--push", default=None, help="HF repo id to upload the result to")
    pq.add_argument("--private", action="store_true", help="push as a private repo")
    pq.add_argument("--no-check", action="store_true", help="skip the GPU pre-flight")

    _add_json_flag(p)
    return p


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    """Give every leaf subcommand `--json`, by walking the parser rather than by hand.

    Hand-writing the flag thirteen times has one failure mode — the fourteenth command
    quietly not getting it — and that is exactly the class of gap this flag exists to
    close. Only LEAVES get it: argparse lets a subparser's default overwrite a parent's
    value for the same dest, so `quantfit calibrate --json sheet` would parse and then
    silently reset `json` to False. `calibrate` alone is not a runnable command, so
    nothing is lost by skipping it.
    """
    subactions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subactions:
        parser.add_argument(
            "--json",
            action="store_true",
            help="emit one JSON document on stdout instead of prose (notices go to stderr)",
        )
        return
    for action in subactions:
        for child in action.choices.values():
            _add_json_flag(child)


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "check":
        from quantfit.fit import capacity_plan

        cap = capacity_plan(args.model, token=args.token)
        code = 0 if cap.fits else 3  # 3 = the doesn't-fit verdict; 2 stays operational-error
        return _emit(
            args,
            "check",
            code,
            {
                "model_id": cap.model_id,
                "fits": cap.fits,
                "mode": cap.mode,
                "limit": cap.limit or None,
                "bytes": {
                    "fp16": cap.fp16_bytes,
                    "gpu_free": cap.gpu_free,
                    "ram_available": cap.ram_available,
                    "disk_free": cap.disk_free,
                    "disk_need": cap.disk_need,
                },
                "reason": cap.reason(),
            },
            lambda: print(cap.reason()),
        )

    if args.cmd == "list":
        from quantfit.registry import METHODS, SCHEMES, catalog

        return _emit(
            args,
            "list",
            0,
            {
                "methods": [
                    {
                        "name": m.name,
                        "backend": m.backend,
                        "default_scheme": m.default_scheme,
                        "needs_calibration": m.needs_calibration,
                        "summary": m.summary,
                    }
                    for m in METHODS.values()
                ],
                "schemes": list(SCHEMES),
            },
            lambda: print(catalog()),
        )

    if args.cmd == "plan":
        from quantfit.engines.base import Budget
        from quantfit.engines.compressed_tensors import CompressedTensorsEngine
        from quantfit.engines.gguf import GgufEngine
        from quantfit.policy.route import route
        from quantfit.policy.target import detect_target

        target = detect_target()
        routed = route(args.model, target, Budget(prefer=args.prefer), [CompressedTensorsEngine(), GgufEngine()])

        def _human_plan() -> None:
            print(f"target: {target.device}/{target.gpu_arch or '-'} serve={target.serve}")
            print(f"pick:   {routed.config.method} {routed.config.scheme}  [{routed.config.engine}]")
            print(f"why:    {routed.rationale}")

        return _emit(
            args,
            "plan",
            0,
            {
                "target": {
                    "device": target.device,
                    "gpu_arch": target.gpu_arch,
                    "vram_bytes": target.vram_bytes,
                    "serve": target.serve,
                },
                "pick": {
                    "method": routed.config.method,
                    "scheme": routed.config.scheme,
                    "engine": routed.config.engine,
                },
                "rationale": routed.rationale,
            },
            _human_plan,
        )

    if args.cmd == "probe":
        from quantfit.policy.probe import probe_sensitivity

        rows = [probe_sensitivity(args.model, bits=bits, token=args.token) for bits in args.bits]

        def _human_probe() -> None:
            print("sensitivity — mean per-token RTN-KL(fp16 || quant); higher = more degradation:")
            for bits, r in zip(args.bits, rows, strict=True):
                print(f"  {bits}-bit: KL {r.mean_kl:.3f}  (n={r.n_samples})")
            print("note: RTN is the worst case — LOW KL = safe bit-width; HIGH KL can over-escalate")
            print("      (calibrated AWQ/GPTQ may still be fine). Read it as sensitivity, not a verdict.")

        return _emit(
            args,
            "probe",
            0,
            {
                "model": args.model,
                "metric": "mean per-token RTN-KL(fp16 || quant)",
                # The caveat travels WITH the numbers. A consumer that reads only the JSON
                # would otherwise get the measurement without the sentence that says a high
                # value is an upper bound, not a verdict.
                "interpretation": (
                    "RTN is the worst case — LOW KL = safe bit-width; HIGH KL can over-escalate "
                    "(calibrated AWQ/GPTQ may still be fine). Read it as sensitivity, not a verdict."
                ),
                "by_bits": [
                    {"bits": bits, "mean_kl": r.mean_kl, "n_samples": r.n_samples}
                    for bits, r in zip(args.bits, rows, strict=True)
                ],
            },
            _human_probe,
        )

    if args.cmd == "verify":
        from quantfit.verify import verify

        ok, msg = verify(args.model)
        code = 0 if ok else 3  # 3 = the smoke-test verdict; 2 stays operational-error
        return _emit(
            args,
            "verify",
            code,
            {"path": args.model, "passed": ok, "message": msg},
            lambda: print(("PASS: " if ok else "FAIL: ") + msg),
        )

    if args.cmd == "verify-safety":
        from quantfit.safety.verify import verify_safety

        if args.demo:
            from quantfit.safety.demo import DEMO_NOTE, demo_drift, demo_summary

            # A demonstration must not be able to leave an artifact a reader could mistake
            # for a measurement, so the flags that write one are refused rather than ignored.
            for flag, value in (("--report", args.report), ("--capture", args.capture), ("--junit", args.junit)):
                if value:
                    raise RuntimeError(
                        f"--demo cannot be combined with {flag}: the demo measures nothing, and an "
                        "artifact it wrote would be indistinguishable from a real run's"
                    )
            demo = demo_drift()
            # Exit 0 regardless of what the fixture shows. The fixture DOES contain a
            # regression — a no-detection demo would teach the output shape but not the
            # shape of a finding — but exit 3 is a verdict about a model, and no model ran.
            return _emit(
                args,
                "verify-safety",
                0,
                {
                    "demo": True,
                    "measured": False,
                    "note": DEMO_NOTE,
                    "regression_detected": demo.regression_detected,
                    "unmeasurable_axes": list(demo.unmeasurable_axes),
                    "summary": demo_summary(demo),
                },
                lambda: print(demo_summary(demo)),
            )

        if not args.baseline or not args.quant:
            raise RuntimeError(
                "verify-safety needs --baseline and --quant. For the report shape without a model, "
                "run `quantfit verify-safety --demo`."
            )

        drift = verify_safety(
            args.baseline,
            args.quant,
            token=args.token,
            max_new_tokens=args.max_new_tokens,
            report_path=args.report,
            capture_path=args.capture,
        )
        # Exit codes are the CI contract; they must not collide with 2 (operational
        # failure, from main's handler) or an unmeasured run would read as a verdict.
        if drift.regression_detected:
            code = 3
        elif drift.unmeasurable_axes:
            code = 4  # zero at-risk pairs on an axis: nothing was measured, not a pass
        else:
            code = 0

        if args.junit:
            from pathlib import Path

            from quantfit.junit import drift_to_junit

            Path(args.junit).write_text(
                drift_to_junit(drift, baseline=args.baseline, quant=args.quant),
                encoding="utf-8",
            )

        def _human_vs() -> None:
            print(drift.summary())  # aggregates only — never echoes raw prompts/completions
            if args.report:
                print(f"report -> {args.report}")
            if args.junit:
                print(f"junit -> {args.junit}")

        return _emit(
            args,
            "verify-safety",
            code,
            {
                # The schema-v2 report is the artifact of record; the envelope carries the
                # same aggregates so a caller need not write a file to read a verdict. Both
                # are aggregates only — no probe text crosses this boundary either way.
                "regression_detected": drift.regression_detected,
                "unmeasurable_axes": list(drift.unmeasurable_axes),
                "summary": drift.summary(),
                "report_path": args.report,
                "capture_path": args.capture,
                "junit_path": args.junit,
            },
            _human_vs,
        )

    if args.cmd == "screen":
        from quantfit.screen import STATUS_REGRESSION, STATUS_UNMEASURABLE, run_screen

        summary = run_screen(
            args.targets,
            args.out,
            token=args.token,
            max_new_tokens=args.max_new_tokens,
            capture_dir=args.capture,
            resume=args.resume,
            attempts=args.attempts,
        )

        if args.junit:
            from pathlib import Path

            from quantfit.junit import screen_to_junit

            Path(args.junit).write_text(screen_to_junit(summary), encoding="utf-8")

        def _human_screen() -> None:
            for stratum, agg in sorted(summary["by_stratum"].items()):
                print(
                    f"{stratum}: {agg['n_completed']}/{agg['n_targets']} completed, "
                    f"{agg['n_operational_errors']} errors"
                )
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
            code = 3
        elif STATUS_UNMEASURABLE in statuses or any(a["n_measured"] == 0 for a in axes):
            code = 4  # an axis nothing was measured on is not a clean screen
        else:
            code = 0
        return _emit(
            args,
            "screen",
            code,
            {**summary, "summary_path": f"{args.out}/screen-summary.json", "junit_path": args.junit},
            _human_screen,
        )

    if args.cmd == "emit":
        from quantfit.modelcard import model_card_fragment

        fragment = model_card_fragment(args.report)
        return _emit(
            args,
            "emit",
            0,
            {"kind": args.what, "report_path": args.report, "fragment": fragment},
            lambda: print(fragment, end=""),  # fragment carries its own trailing newline
        )

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

        if args.junit:
            from pathlib import Path

            from quantfit.junit import gate_to_junit

            Path(args.junit).write_text(
                gate_to_junit(decision, baseline=args.baseline, quant=args.quant),
                encoding="utf-8",
            )

        def _human_gate() -> None:
            print(decision["headline"])
            if args.out:
                print(f"gate decision -> {args.out}")
            if args.junit:
                print(f"junit -> {args.junit}")

        return _emit(
            args,
            "gate",
            decision["exit_code"],
            {**decision, "decision_path": args.out, "report_path": args.report, "junit_path": args.junit},
            _human_gate,
        )

    if args.cmd == "calibrate":
        if args.calibrate_cmd == "sheet":
            from quantfit.safety.calibrate import build_labeling_sheet

            sheet, key = build_labeling_sheet(args.capture, args.sheet, args.key)

            def _human_sheet() -> None:
                print(f"blinded sheet -> {sheet}")
                print(f"unblinding key -> {key} (labeler never sees this file)")

            return _emit(
                args,
                "calibrate sheet",
                0,
                {
                    "subcommand": "sheet",
                    "capture_path": args.capture,
                    "sheet_path": str(sheet),
                    "key_path": str(key),
                    # Said in the payload as well as the prose: a caller that automates this
                    # must not treat the key as an ordinary output to ship alongside the sheet.
                    "note": "the labeler never sees the key file; blinding depends on it",
                },
                _human_sheet,
            )
        from quantfit.safety.calibrate import ingest_labels

        report = ingest_labels(args.sheet, args.key, args.out)

        def _human_ingest() -> None:
            for arm in ("baseline", "quantized"):
                block = report[arm]
                eps = block["epsilon"]
                print(
                    f"{arm}: n={block['n']} judge_errors={block['judge_errors']} "
                    f"epsilon={'unmeasured' if eps is None else f'{eps:.4f}'}"
                )
            print(f"calibration report -> {args.out} (counts only, no completion text)")

        return _emit(
            args,
            "calibrate ingest",
            0,
            {**report, "subcommand": "ingest", "report_path": args.out},
            _human_ingest,
        )

    if args.cmd == "reproduce":
        from quantfit.reproduce import compare, within_hardware_identical

        # Replicate sets are turned into T0 results HERE rather than inside compare():
        # T0 is a within-hardware property of three runs, and keeping the conversion at
        # the boundary is what lets the artifact record which files supplied it.
        t0_ref = within_hardware_identical(args.t0_reference) if args.t0_reference else None
        t0_cand = within_hardware_identical(args.t0_candidate) if args.t0_candidate else None
        decision = compare(args.reference, args.candidate, args.out, t0_reference=t0_ref, t0_candidate=t0_cand)

        def _human_reproduce() -> None:
            print(decision["headline"])
            if args.out:
                print(f"comparison record -> {args.out}")

        return _emit(
            args,
            "reproduce",
            decision["exit_code"],
            {**decision, "record_path": args.out},
            _human_reproduce,
        )

    if args.cmd == "audit":
        from pathlib import Path

        from quantfit.audit import audit, summarize

        result = audit(args.root)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        def _human_audit() -> None:
            print(summarize(result))
            if args.json_out:
                print(f"audit findings -> {args.json_out}")

        return _emit(
            args,
            "audit",
            result["exit_code"],
            {**result, "findings_path": args.json_out},
            _human_audit,
        )

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
            return _emit_error(args, str(exc), type(exc).__name__)
        pushed = push(str(out), args.push, token=args.token, private=args.private) if args.push else None

        def _human_quantize() -> None:
            print(f"quantized -> {out}")
            if pushed:
                print(f"pushed -> {pushed}")

        return _emit(
            args,
            "quantize",
            0,
            {
                "model": args.model,
                "method": args.method,
                "scheme": args.scheme,
                "out": str(out),
                "pushed_to": pushed,
            },
            _human_quantize,
        )

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
        return _emit_error(args, str(exc), type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
