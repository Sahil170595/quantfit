"""Command surface for CPU weight-space operations. Numerical imports are lazy."""

from __future__ import annotations


def add_parser(commands):
    parser = commands.add_parser("weightspace", help="Encode and reconstruct local model weights.")
    sub = parser.add_subparsers(dest="weight_cmd", required=True)
    enc = sub.add_parser("encode", help="Create a new directory containing a portable checkpoint delta.")
    enc.add_argument("--base", required=True, help="Base SafeTensors checkpoint.")
    enc.add_argument("--target", required=True, help="Target SafeTensors checkpoint.")
    enc.add_argument("--out", required=True, help="New bundle directory.")
    enc.add_argument("--codec", choices=["xor-bytes-v1", "task-vector-v1", "grouped-int-v1"], default="xor-bytes-v1")
    enc.add_argument("--bits", type=int, choices=[4, 8], help="Signed group code width (default 4).")
    enc.add_argument("--group-size", type=int, help="Elements per quantization group (default 64).")
    comp = sub.add_parser("compile-head", help="Fit and export a standalone smaller classifier.")
    comp.add_argument("--spec", required=True, help="Local JSON compiler input.")
    comp.add_argument("--out", required=True, help="New recipient bundle directory.")
    bench = sub.add_parser("benchmark-heads", help="Compare classifiers at matched offline query budgets.")
    bench.add_argument("--spec", required=True, help="Local benchmark partitions, seeds and budgets in JSON.")
    pred = sub.add_parser("predict-head", help="Verify a standalone recipient and score raw text.")
    pred.add_argument("--artifact", required=True, help="Recipient manifest.json path.")
    pred.add_argument("--input-text", required=True, help="Raw text to classify.")
    dec = sub.add_parser("decode", help="Verify a delta and recover a new SafeTensors checkpoint.")
    dec.add_argument("--base", required=True, help="Base SafeTensors checkpoint.")
    dec.add_argument("--artifact", required=True, help="Bundle manifest.json path.")
    dec.add_argument("--scale", type=float, default=1.0, help="Multiplier applied to a numerical update.")
    dec.add_argument("--out", required=True, help="New SafeTensors output file.")


def run(args, emit):
    from quantfit.weightspace import benchmark_heads, compile_head, decode, encode, predict_head
    from quantfit.weightspace.head import load_spec, require

    if args.weight_cmd == "encode":
        result = encode(args.base, args.target, args.out, codec=args.codec, bits=args.bits, group_size=args.group_size)
    elif args.weight_cmd == "benchmark-heads":
        result = benchmark_heads(load_spec(args.spec))
        return emit(
            args,
            "weightspace/benchmark-heads",
            0,
            result,
            lambda: print(f"{len(result['trials'])} trials, {result['held_out_cases']} held-out cases"),
        )
    elif args.weight_cmd == "compile-head":
        spec = load_spec(args.spec)
        required = {"recipient_anchors", "donor_anchors", "donor_weight", "donor_bias", "vocabulary", "labels"}
        require(required <= spec.keys() <= required | {"lowercase"}, "incorrect compiler input fields")
        result = compile_head(out=args.out, **spec)
    elif args.weight_cmd == "predict-head":
        result = predict_head(args.artifact, args.input_text)
    else:
        result = decode(args.base, args.artifact, args.out, scale=args.scale)
    return emit(
        args,
        f"weightspace/{args.weight_cmd}",
        0,
        result,
        lambda: print(
            result["label"]
            if args.weight_cmd == "predict-head"
            else f"{args.weight_cmd}: {result['codec']} -> {args.out}"
        ),
    )
