"""quantfit CLI — check / list / plan / probe / quantize / verify / verify-safety / screen / emit."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from quantfit import __version__  # plain module-level string; the heavy surface stays lazy
from quantfit.gate import TIERS as GATE_TIERS  # tier NAMES only — no torch, no heavy import
from quantfit.policy.probe import DEFAULT_PROBE_SAMPLES, DEFAULT_PROBE_SEQLEN  # constants; torch loads in the probe
from quantfit.registry import METHODS
from quantfit.spec import DEFAULT_SPEC  # a frozen dataclass of constants

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


_BASELINE_CACHE_HELP = (
    "GGUF pairs only: reuse the baseline arm's completions from DIR when this exact arm, "
    "environment, probe set and decode were generated before, and store them when not. A hit "
    "skips baseline generation; budgets assume zero hits. Entries hold completion text: "
    "local-only, never commit them (*.baseline-cache.json is gitignored)"
)


def _positive_int(text: str) -> int:
    # `--samples 0` would reach the probe as an empty batch and fail as "calibration dataset
    # returned no usable rows" - blaming the dataset for the caller's argument.
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


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
    ppr.add_argument(
        "--samples",
        type=_positive_int,
        default=DEFAULT_PROBE_SAMPLES,
        metavar="N",
        help=f"packed {DEFAULT_PROBE_SEQLEN}-token calibration blocks the KL is averaged over, per bit-width "
        f"(default {DEFAULT_PROBE_SAMPLES}). Host RAM grows with N: each block's reference logits are held "
        "on the CPU for the whole run",
    )

    pv = sub.add_parser(
        "verify",
        help="smoke-load a quantized artifact + generate (GGUF: structural magic check only) "
        "(exit 0 = pass, 3 = fail, 2 = operational error)",
    )
    pv.add_argument("--model", required=True, help="path to a quantized output dir or .gguf")

    pinspect = sub.add_parser(
        "inspect-run",
        parents=[tok],
        help="observed HF Inspect paired run (same 0/2/3/4 exits as verify-safety)",
    )
    pinspect.add_argument("--baseline", default=None, help="Inspect HF spec: hf/org/repo")
    pinspect.add_argument("--quant", default=None, help="Inspect HF spec: hf/org/repo")
    pinspect.add_argument("--baseline-revision", default=None, help="immutable baseline HF commit SHA")
    pinspect.add_argument("--quant-revision", default=None, help="immutable quantized HF commit SHA")
    pinspect.add_argument("--max-new-tokens", type=int, default=64)
    pinspect.add_argument("--report", default=None, metavar="PATH", help="write aggregate-only schema-v2 report")
    pinspect.add_argument(
        "--log-dir", default=None, metavar="DIR", help="LOCAL capture-class Inspect logs; never commit"
    )

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
    pvs.add_argument("--baseline-cache", default=None, metavar="DIR", help=_BASELINE_CACHE_HELP)
    pvs.add_argument("--baseline-revision", default=None, help="immutable 40-hex commit; Hub GGUF refs only")
    pvs.add_argument("--quant-revision", default=None, help="immutable 40-hex commit; Hub GGUF refs only")

    pcold = sub.add_parser("cold-run", help="three fresh uncached native GGUF children + T0; POSIX only")
    pcold.add_argument("--baseline", required=True, help="unquantized GGUF path or hf: GGUF ref")
    pcold.add_argument("--quant", required=True, help="quantized GGUF path or hf: GGUF ref")
    pcold.add_argument("--baseline-revision", default=None, help="immutable Hub GGUF commit; refuses local pins")
    pcold.add_argument("--quant-revision", default=None, help="immutable Hub GGUF commit; refuses local pins")
    pcold.add_argument("--out", required=True, metavar="NEW_DIR", help="new aggregate output directory")
    pcold.add_argument("--timeout-seconds", type=float, default=3600, help="deadline per child (default 3600)")
    pcold.add_argument("--max-new-tokens", type=_positive_int, default=64)

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
    pe.add_argument(
        "--calibration-report",
        metavar="PATH",
        help="bound schema-2 calibration for separately labeled conditional resolution; no human-label authentication",
    )

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
    pg.add_argument(
        "--calibration-report",
        default=None,
        metavar="PATH",
        help="bound schema-2 calibration report; mutually exclusive with --eps-upper/--eps-source. "
        "Scope matching does not verify human labels or sensitivity",
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
    pg.add_argument("--baseline-cache", default=None, metavar="DIR", help=_BASELINE_CACHE_HELP)

    pres = sub.add_parser(
        "resolution",
        help="offline conditional resolution from a drift report and bound calibration (exit 0 = analysis completed, 2 = operational error)",
    )
    pres.add_argument("--report", required=True, metavar="PATH", help="existing schema-v2 drift report")
    pres.add_argument(
        "--calibration-report",
        required=True,
        metavar="PATH",
        help="bound calibration report matching the actual measurement scope",
    )
    pres.add_argument(
        "--out", required=True, metavar="PATH", help="separate resolution artifact; must not overwrite either input"
    )

    pt0 = sub.add_parser(
        "t0",
        help="check at least three uncached same-environment replicate reports "
        "(exit 0 = agreement, 3 = disagreement, 2 = invalid evidence)",
    )
    pt0.add_argument("--reports", nargs="+", required=True, metavar="REPORT", help="three or more replicate reports")
    pt0.add_argument("--out", required=True, metavar="PATH", help="write the aggregate T0 evidence JSON")

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
        metavar="PATH",
        help="one standalone T0 artifact, or within-hardware replicate reports for the REFERENCE side "
        "(3 per the protocol). Positive evidence must bind to the compared report",
    )
    pr.add_argument(
        "--t0-candidate",
        nargs="+",
        default=None,
        metavar="PATH",
        help="one standalone T0 artifact, or within-hardware replicate reports for the CANDIDATE side",
    )

    pref = sub.add_parser("references", help="offline reference registry and exact artifact-byte verification")
    rsub = pref.add_subparsers(dest="references_cmd", required=True)
    rlist = rsub.add_parser("list", help="list declared reference entries and spec validity")
    rverify = rsub.add_parser("verify", help="verify local bytes against a declared reference digest")
    for child in (rlist, rverify):
        child.add_argument(
            "--registry", default=None, metavar="PATH", help="external registry JSON; default: bundled registry"
        )
    rverify.add_argument("--slug", required=True, help="registered reference slug")
    rverify.add_argument("--report", required=True, metavar="PATH", help="local artifact bytes to verify")

    pbundle = sub.add_parser(
        "bundle", help="offline portable aggregate evidence; integrity success is no scientific GO"
    )
    bsub = pbundle.add_subparsers(dest="bundle_cmd", required=True)
    bcreate = bsub.add_parser("create", help="create a new exact-byte aggregate bundle (0 done, 2 unsupported input)")
    bcreate.add_argument(
        "--report", default=None, metavar="PATH", help="aggregate schema-2 report; omitted only for pre-run refusal"
    )
    bcreate.add_argument("--out", required=True, metavar="DIR", help="new bundle directory; parent must exist")
    bcreate.add_argument("--calibration-report", metavar="PATH", help="optional bound schema-2 aggregate calibration")
    bcreate.add_argument(
        "--gate", metavar="PATH", help="optional aggregate gate decision; original no-answer states survive"
    )
    bcreate.add_argument(
        "--resolution", metavar="PATH", help="optional conditional analysis; requires calibration input"
    )
    bverify = bsub.add_parser(
        "verify", help="verify relocated bundle (0 intact, 3 byte mismatch, 2 unsupported/unsafe)"
    )
    bverify.add_argument("--bundle", required=True, metavar="DIR", help="local portable bundle directory")

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

        rows = [
            probe_sensitivity(args.model, bits=bits, n_samples=args.samples, token=args.token) for bits in args.bits
        ]

        def _human_probe() -> None:
            print(
                f"sensitivity — mean per-token RTN-KL(fp16 || quant) over packed {DEFAULT_PROBE_SEQLEN}-token "
                "blocks; higher = more degradation:"
            )
            for bits, r in zip(args.bits, rows, strict=True):
                s = r.spread
                spread = (
                    f", range {s['kl_min']:.3f}-{s['kl_max']:.3f}, sd {s['kl_sd']:.3f}"
                    if s["kl_sd"] is not None
                    else ""
                )
                # The dataset can run out of usable rows before N; the mean is then over fewer,
                # and saying "n=40" alone would let a reader assume 40 is what was asked for.
                short = f" of {args.samples} requested" if r.n_samples < args.samples else ""
                print(f"  {bits}-bit: KL {r.mean_kl:.3f}  (n={r.n_samples}{short}{spread})")
            revisions = {r.model_revision for r in rows}
            if len(revisions) > 1:
                # Each bit-width loads the model afresh; a `main` that moved mid-run means the
                # rows are over different weights and must not be compared.
                print("model revision DIFFERS between bit-widths: " + ", ".join(sorted(map(str, revisions))))
            else:
                (revision,) = revisions
                print(f"model revision: {revision or 'not resolved (a local path has no Hub commit)'}")
            print("note: RTN is the worst case — LOW KL = safe bit-width; HIGH KL can over-escalate")
            print("      (calibrated AWQ/GPTQ may still be fine). Read it as sensitivity, not a verdict.")

        return _emit(
            args,
            "probe",
            0,
            {
                "model": args.model,
                # Named for what it is since 0.15.0: before, the mean was over variable-length
                # rows, and those numbers are a different metric, not a noisier copy of this one.
                "metric": f"mean per-token RTN-KL(fp16 || quant) over packed {DEFAULT_PROBE_SEQLEN}-token blocks",
                "requested_samples": args.samples,
                # Which tokens the KL was averaged over is a measurement input; the record that
                # found the old tail was short rows had to reconstruct this by hand.
                "calibration": {
                    "dataset": DEFAULT_SPEC.calib_dataset,
                    "config": DEFAULT_SPEC.calib_config,
                    "split": DEFAULT_SPEC.calib_split,
                    "revision": DEFAULT_SPEC.calib_revision,
                    "shuffle_seed": DEFAULT_SPEC.seed,
                    "packing": "the quantize path's: rows concatenated, chunked into fixed-length blocks",
                    "block_tokens": DEFAULT_PROBE_SEQLEN,
                },
                # The caveat travels WITH the numbers. A consumer that reads only the JSON
                # would otherwise get the measurement without the sentence that says a high
                # value is an upper bound, not a verdict.
                "interpretation": (
                    "RTN is the worst case — LOW KL = safe bit-width; HIGH KL can over-escalate "
                    "(calibrated AWQ/GPTQ may still be fine). Read it as sensitivity, not a verdict."
                ),
                "by_bits": [
                    {
                        "bits": bits,
                        "mean_kl": r.mean_kl,
                        "n_samples": r.n_samples,
                        **r.spread,
                        "per_sample_kl": list(r.per_sample_kl),
                        # Per row: each bit-width is its own load, and `main` can move between.
                        "model_revision": r.model_revision,
                    }
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

    if args.cmd == "inspect-run":
        import contextlib
        import tempfile
        from pathlib import Path

        from quantfit.inspect_task import qsr_eval

        if not args.baseline or not args.quant:
            raise RuntimeError("inspect-run needs --baseline and --quant HF specs")
        if not args.baseline_revision or not args.quant_revision:
            raise RuntimeError("inspect-run needs both immutable --baseline-revision and --quant-revision")
        # Temporary logs disappear even on failure. Explicit logs are local-only
        # captures; stdout must remain exactly one JSON envelope.
        with contextlib.ExitStack() as stack:
            log_dir = args.log_dir or stack.enter_context(
                tempfile.TemporaryDirectory(prefix="quantfit-inspect-capture-")
            )
            if args.log_dir:
                print(
                    "Inspect logs contain probe/completion text: local-only; never commit or attach them.",
                    file=sys.stderr,
                )
            with contextlib.redirect_stdout(sys.stderr):
                run = qsr_eval(
                    args.baseline,
                    args.quant,
                    token=args.token,
                    max_new_tokens=args.max_new_tokens,
                    hf_revisions=(args.baseline_revision, args.quant_revision),
                    log_dir=log_dir,
                    display="none",
                    max_samples=1,
                )
                if run.observed_arms is None:
                    raise RuntimeError("Inspect did not return actual loaded arm observations")
                if args.report:
                    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
                    run.write_report(args.report, *run.observed_arms, args.max_new_tokens)
            code = 3 if run.drift.regression_detected else 4 if run.drift.unmeasurable_axes else 0
            return _emit(
                args,
                "inspect-run",
                code,
                {
                    "regression_detected": run.drift.regression_detected,
                    "unmeasurable_axes": list(run.drift.unmeasurable_axes),
                    "summary": run.drift.summary(),
                    "report_path": args.report,
                    "log_dir": args.log_dir,
                    "observed": True,
                },
                lambda: print(run.drift.summary()),
            )

    if args.cmd == "cold-run":
        from quantfit.cold_run import cold_run

        result = cold_run(
            args.baseline,
            args.quant,
            args.out,
            timeout_seconds=args.timeout_seconds,
            max_new_tokens=args.max_new_tokens,
            baseline_revision=args.baseline_revision,
            quant_revision=args.quant_revision,
        )
        return _emit(
            args,
            "cold-run",
            result["exit_code"],
            result,
            lambda: print(f"{result['status']} -> {args.out}; native exits remain separate from T0"),
        )

    if args.cmd == "verify-safety":
        from quantfit.safety.verify import verify_safety

        if args.demo:
            from quantfit.safety.demo import DEMO_NOTE, demo_drift, demo_summary

            # A demonstration must not be able to leave an artifact a reader could mistake
            # for a measurement, so the flags that write one are refused rather than ignored.
            for flag, value in (
                ("--report", args.report),
                ("--capture", args.capture),
                ("--junit", args.junit),
                ("--baseline-cache", args.baseline_cache),
                ("--baseline-revision", args.baseline_revision),
                ("--quant-revision", args.quant_revision),
            ):
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

        revisions = {}
        if args.baseline_revision is not None:
            revisions["baseline_revision"] = args.baseline_revision
        if args.quant_revision is not None:
            revisions["quant_revision"] = args.quant_revision
        drift = verify_safety(
            args.baseline,
            args.quant,
            token=args.token,
            max_new_tokens=args.max_new_tokens,
            report_path=args.report,
            capture_path=args.capture,
            baseline_cache_dir=args.baseline_cache,
            **revisions,
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
                    print(
                        f"  {axis}: {a['n_regressed']}/{a['n_measured']} flagged "
                        f"(95% CI {lo * 100:.1f}-{hi * 100:.1f}%)"
                    )
                    # BOTH caveats, not just `conditionality`. 0.12.3 added
                    # `resolution_caveat` to the JSON and this line kept printing only
                    # `conditionality` -- so on a PASSED control (which clears
                    # conditionality and nothing else) the terminal printed a bare,
                    # unqualified-looking bound. That is the exact failure 0.12.3 was
                    # written to close, still live on the surface a human actually reads.
                    #
                    # Indexed, not `.get`: `run_screen` always emits the key, and a
                    # silently omitted caveat is a worse outcome here than a KeyError.
                    for caveat in (a["conditionality"], a["resolution_caveat"]):
                        if caveat:
                            print(f"      [{caveat}]")
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

        fragment = (
            model_card_fragment(args.report, calibration_report=args.calibration_report)
            if args.calibration_report is not None
            else model_card_fragment(args.report)
        )
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
            calibration_report=args.calibration_report,
            token=args.token,
            max_new_tokens=args.max_new_tokens,
            report_path=args.report,
            out_path=args.out,
            baseline_cache_dir=args.baseline_cache,
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

    if args.cmd == "bundle":
        from quantfit.bundle import create_bundle, verify_bundle

        result = (
            create_bundle(
                args.report,
                args.out,
                calibration_path=args.calibration_report,
                gate_path=args.gate,
                resolution_path=args.resolution,
            )
            if args.bundle_cmd == "create"
            else verify_bundle(args.bundle)
        )
        code = 0 if result["integrity_verified"] else 3

        def human_bundle():
            print("Bundle integrity: " + ("MATCH" if result["integrity_verified"] else "MISMATCH"))
            print(result["scope"])

        return _emit(args, "bundle", code, result, human_bundle)

    if args.cmd == "resolution":
        from quantfit.resolution import analyze_resolution

        result = analyze_resolution(args.report, args.calibration_report, args.out)

        def human_resolution():
            for name, axis in result["axes"].items():
                print(f"{name}: {axis['flagged_flips']}/{axis['n_at_risk']} flagged flips")
                print(f"  {axis['resolution']['headline']}")
            print("Conditional analysis; calibration label truth and statistical assumptions are not verified.")
            print(f"resolution artifact -> {args.out}")

        return _emit(args, "resolution", 0, result, human_resolution)

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

    if args.cmd == "t0":
        from quantfit.reproduce import T0_REQUIRED_REPLICATES, ReproduceError, within_hardware_identical

        if len(args.reports) < T0_REQUIRED_REPLICATES:
            raise ReproduceError(
                f"t0 requires at least {T0_REQUIRED_REPLICATES} replicate reports; got {len(args.reports)}"
            )
        result = within_hardware_identical(args.reports, out_path=args.out)

        def _human_t0() -> None:
            print(f"T0: {'agreement' if result['pass'] else 'DISAGREEMENT'} across {result['n_replicates']} reports")
            print(result["statement"])
            print(f"T0 evidence -> {args.out}")

        return _emit(args, "t0", 0 if result["protocol_pass"] else 3, {**result, "record_path": args.out}, _human_t0)

    if args.cmd == "reproduce":
        from pathlib import Path

        from quantfit.reproduce import ReproduceError, compare, within_hardware_identical

        def _t0_input(paths):
            if not paths:
                return None
            if len(paths) > 1:
                return within_hardware_identical(paths)
            # Keep existing report-list invocations; a single path now consumes the
            # standalone artifact. compare rechecks positive sources and target binding.
            try:
                value = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError) as exc:
                raise ReproduceError(f"unreadable T0 artifact {paths[0]}: {exc}") from exc
            if isinstance(value, bool) or (isinstance(value, dict) and isinstance(value.get("pass"), bool)):
                return value
            raise ReproduceError("one T0 input must be a standalone artifact; otherwise supply replicate report paths")

        t0_ref = _t0_input(args.t0_reference)
        t0_cand = _t0_input(args.t0_candidate)
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

    if args.cmd == "references":
        from quantfit.reference_cli import list_references, verify_reference

        if args.references_cmd == "list":
            result = list_references(args.registry)
            code = 0
            message = result["registry_state"] or f"{result['n_registered']} declared reference reports"
        else:
            result = verify_reference(args.slug, args.report, args.registry)
            code = 0 if result["matches"] else 3
            message = result["statement"]
        return _emit(args, f"references {args.references_cmd}", code, result, lambda: print(message))

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
    except (RuntimeError, OSError, ImportError) as exc:
        # Operational failures (no GPU, gated/missing model, network, disk, short
        # calibration/probe datasets — quantfit raises its own as RuntimeError) ->
        # a clean message + exit 2, not a traceback. Programming errors, including
        # ValueError from anywhere in the torch/transformers stack, surface raw.
        #
        # ImportError joined the tuple on 2026-08-21, matching the same widening
        # `quantfit/screen.py` made for the same reason. A missing optional dependency
        # is a fact about the host, not a defect in quantfit: gptqmodel's AWQ kernel
        # imports triton, which does not ship on Windows, and a user meeting that
        # deserves "exit 2, here is what is missing" rather than a traceback ending in
        # somebody else's module. Exit 1 also breaks the documented CI contract, which
        # says operational failures exit 2 — a caller distinguishing "the tool broke"
        # from "the measurement says no" cannot do it on a traceback.
        #
        # Still NOT widened to bare Exception: a ValueError from the torch stack is a
        # programming error and must keep surfacing raw, or a real bug would be
        # reported to the user as an operational problem with their machine.
        return _emit_error(args, str(exc), type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
