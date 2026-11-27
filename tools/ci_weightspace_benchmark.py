"""Run a paired offline classifier comparison and independently recompute its outcomes."""

import json
from importlib.metadata import version

from quantfit.weightspace import benchmark_heads


def fixture():
    def rows(start, end, kind):
        indices = list(range(start, end))
        points = [(29 * i + 3) % 64 for i in indices]
        rec = [[float(i % 8), float(i // 8)] for i in points]
        donor = [[x, y, x - y + 1] for x, y in rec]
        labels = [int(2 * x - y < -x + 3 * y - 0.5) for x, y in rec]
        return {
            "ids": [f"case-{i}" for i in indices],
            "recipient": rec,
            **({"donor": donor} if kind != "held" else {}),
            **({"labels": labels} if kind != "archive" else {}),
        }

    return {
        "archive": rows(0, 16, "archive"),
        "queries": rows(16, 48, "queries"),
        "held_out": rows(48, 64, "held"),
        "donor_weight": [[1, 0, 1], [0, 2, -1]],
        "donor_bias": [-1, 0.5],
        "wrong_donor_weight": [[0, 2, -1], [1, 0, 1]],
        "wrong_donor_bias": [0.5, -1],
        "labels": ["first", "second"],
        "budgets": [0, 4, 32],
        "seeds": [7, 19],
    }


def check():
    spec = fixture()
    assert len(set(spec["held_out"]["labels"])) == 2
    paired = []
    result = benchmark_heads(spec, observe=paired.append)
    for trial, rows in zip(result["trials"], paired):
        assert len(set(rows["query_ids"])) == trial["budget"]
        expected = dict(zip(spec["held_out"]["ids"], spec["held_out"]["labels"]))
        for arm, scores in trial["arms"].items():
            wins = ties = losses = correct = 0
            for cid, a, b in zip(rows["ids"], rows["predictions"][arm], rows["predictions"]["compiled_adapted"]):
                gold = expected[cid]
                correct += int(a == gold)
                if (a == gold) == (b == gold):
                    ties += 1
                elif b == gold:
                    wins += 1
                else:
                    losses += 1
            assert (correct, wins, ties, losses) == tuple(
                scores[k] for k in ("correct", "reference_wins", "ties", "reference_losses")
            )
        assert trial["arms"]["compiled"]["correct"] == len(expected)
    return result


def main():
    print(json.dumps({"version": version("quantfit"), **check()}))


if __name__ == "__main__":
    main()
