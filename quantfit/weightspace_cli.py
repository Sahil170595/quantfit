"""Command surface for CPU weight-space operations. Numerical imports are lazy."""

from __future__ import annotations


def add_parser(commands):
    parser = commands.add_parser("weightspace", help="Encode and reconstruct local model weights.")
    sub = parser.add_subparsers(dest="weight_cmd", required=True)
    enc = sub.add_parser("encode", help="Create a new directory containing a portable checkpoint delta.")
    enc.add_argument("--base", required=True, help="Base SafeTensors checkpoint.")
    enc.add_argument("--target", required=True, help="Target SafeTensors checkpoint.")
    enc.add_argument("--out", required=True, help="New bundle directory.")
    dec = sub.add_parser("decode", help="Verify a delta and recover a new SafeTensors checkpoint.")
    dec.add_argument("--base", required=True, help="Base SafeTensors checkpoint.")
    dec.add_argument("--artifact", required=True, help="Bundle manifest.json path.")
    dec.add_argument("--out", required=True, help="New SafeTensors output file.")


def run(args, emit):
    from quantfit.weightspace import decode, encode

    if args.weight_cmd == "encode":
        result = encode(args.base, args.target, args.out)
    else:
        result = decode(args.base, args.artifact, args.out)
    return emit(
        args,
        f"weightspace/{args.weight_cmd}",
        0,
        result,
        lambda: print(f"{args.weight_cmd}: {result['codec']} -> {args.out}"),
    )
