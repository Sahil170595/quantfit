"""Offline paired evaluation with separate archive, target-query and held-out partitions."""

from __future__ import annotations

import numpy as np

from ._tensors import canonical, require, sha
from .head import affine, compose, numeric


def integer_list(value, name, minimum, maximum):
    require(
        isinstance(value, list) and value and all(type(i) is int and minimum <= i <= maximum for i in value),
        f"invalid {name}",
    )
    require(len(set(value)) == len(value), f"duplicate {name}")
    return value


def partition(data, name, features, classes):
    require(isinstance(data, dict) and data.keys() == {"ids", "recipient", *features}, f"incorrect {name} fields")
    ids = data["ids"]
    require(
        isinstance(ids, list) and all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids),
        f"invalid {name} IDs",
    )
    result = {"ids": ids, "recipient": numeric(data["recipient"], 2, f"{name} recipient")}
    require(len(result["recipient"]) == len(ids), f"{name} case count mismatch")
    if "donor" in features:
        result["donor"] = numeric(data["donor"], 2, f"{name} donor")
        require(len(result["donor"]) == len(ids), f"{name} donor count mismatch")
    if "labels" in features:
        labels = data["labels"]
        require(
            isinstance(labels, list)
            and len(labels) == len(ids)
            and all(type(i) is int and 0 <= i < classes for i in labels),
            f"invalid {name} label indices",
        )
        result["labels"] = np.asarray(labels)
    return result


def score(data, coeff):
    result = data @ coeff[:-1] + coeff[-1]
    require(np.isfinite(result).all(), "nonfinite classifier scores")
    return result


def classify(data, head):
    # Match the runnable recipient's row-wise float32 dot followed by float32 bias.
    with np.errstate(over="ignore", invalid="ignore"):
        w = np.ascontiguousarray(head[:-1].T, dtype="<f4")
        b = head[-1].astype("<f4")
        rows = np.asarray([w @ row.astype("<f4") + b for row in data])
    require(np.isfinite(rows).all(), "nonfinite recipient evaluation logits")
    return np.argmax(rows, axis=1)


def coefficients(rec, donor, w, b):
    small_w, small_b, _ = compose(rec, donor, w, b)
    return np.vstack([small_w.T, small_b]).astype("f8")


def fit_residual(prior, x, y):
    if len(x) == 0:
        return prior
    correction, _ = affine(x, y - score(x, prior))
    return prior + correction


def benchmark_heads(spec, *, observe=None):
    """Score eight CPU arms. Optional local observer receives paired rows, excluded from the returned aggregate."""
    required = {
        "archive",
        "queries",
        "held_out",
        "donor_weight",
        "donor_bias",
        "wrong_donor_weight",
        "wrong_donor_bias",
        "labels",
        "seeds",
        "budgets",
    }
    require(isinstance(spec, dict) and spec.keys() == required, "incorrect benchmark fields")
    labels = spec["labels"]
    require(
        isinstance(labels, list)
        and len(labels) >= 2
        and all(isinstance(n, str) and n for n in labels)
        and len(set(labels)) == len(labels),
        "expected at least two ordered distinct class labels",
    )
    nc = len(labels)
    archive = partition(spec["archive"], "archive", {"donor"}, nc)
    queries = partition(spec["queries"], "queries", {"donor", "labels"}, nc)
    held = partition(spec["held_out"], "held-out", {"labels"}, nc)
    ids = archive["ids"] + queries["ids"] + held["ids"]
    require(len(set(ids)) == len(ids), "archive, query and evaluation IDs must be disjoint")
    ar, ad = archive["recipient"], archive["donor"]
    require(len(ar) >= 2, "need at least two anchors for the shuffled control")
    width, donor_width = ar.shape[1], ad.shape[1]
    require(
        width < donor_width
        and queries["recipient"].shape[1] == held["recipient"].shape[1] == width
        and queries["donor"].shape[1] == donor_width,
        "incompatible feature widths",
    )
    w, b = numeric(spec["donor_weight"], 2, "donor weight"), numeric(spec["donor_bias"], 1, "donor bias")
    wrong_w, wrong_b = (
        numeric(spec["wrong_donor_weight"], 2, "wrong donor weight"),
        numeric(spec["wrong_donor_bias"], 1, "wrong donor bias"),
    )
    require(
        w.shape == wrong_w.shape == (nc, donor_width) and b.shape == wrong_b.shape == (nc,),
        "invalid donor head dimensions",
    )
    require(
        not (np.array_equal(w, wrong_w) and np.array_equal(b, wrong_b)), "wrong-donor control must use a distinct head"
    )
    seeds = integer_list(spec["seeds"], "seeds", 0, 2**32 - 1)
    budgets = integer_list(spec["budgets"], "budgets", 0, len(queries["ids"]))
    donor = np.vstack([w.T, b])
    archive_logits = score(ad, donor)
    dense = coefficients(ar, ad, w, b)
    wrong = coefficients(ar, ad, wrong_w, wrong_b)
    scores_only, _ = affine(ar, archive_logits)
    zero = np.zeros((width + 1, nc))
    results = []
    target_cache = {}
    archive_arms = {"compiled", "compiled_adapted", "wrong_donor", "shuffled_anchors", "output_only_matched"}
    uses_queries = {"compiled_adapted", "wrong_donor", "shuffled_anchors", "output_only_matched", "output_only_target"}
    for seed in seeds:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(queries["ids"]))
        shuffled_order = rng.permutation(len(ar))
        shuffled_donor = ad.copy()
        shuffled_donor[shuffled_order] = ad[np.roll(shuffled_order, 1)]
        shuffled = coefficients(ar, shuffled_donor, w, b)
        random_head = rng.standard_normal(zero.shape)
        for budget in budgets:
            chosen = order[:budget]
            for index in chosen:
                if int(index) not in target_cache:
                    target_cache[int(index)] = score(queries["donor"][index], donor)
            x = queries["recipient"][chosen]
            teacher = np.asarray([target_cache[int(i)] for i in chosen]).reshape(budget, nc)
            # Fit only selected labels. Evaluation labels first enter the correctness calculation below.
            native = np.zeros((budget, nc))
            native[np.arange(budget), queries["labels"][chosen]] = 1
            heads = {
                "compiled": dense,
                "compiled_adapted": fit_residual(dense, x, teacher),
                "random": random_head,
                "wrong_donor": fit_residual(wrong, x, teacher),
                "shuffled_anchors": fit_residual(shuffled, x, teacher),
                "labeled_student": fit_residual(zero, x, native),
                "output_only_matched": fit_residual(scores_only, x, teacher),
                "output_only_target": fit_residual(zero, x, teacher),
            }
            preds = {name: classify(held["recipient"], head) for name, head in heads.items()}
            correct = {name: pred == held["labels"] for name, pred in preds.items()}
            reference = correct["compiled_adapted"]
            arms = {}
            for name, mask in correct.items():
                arms[name] = {
                    "correct": int(mask.sum()),
                    "cases": len(mask),
                    "accuracy": float(mask.mean()),
                    "reference_wins": int((reference & ~mask).sum()),
                    "ties": int((reference == mask).sum()),
                    "reference_losses": int((~reference & mask).sum()),
                    "archive_cases_available": len(ar),
                    "archive_cases_used": len(ar) if name in archive_arms else 0,
                    "archive_logit_queries": len(ar) if name == "output_only_matched" else 0,
                    "target_logit_queries": budget if name in uses_queries else 0,
                    "target_gold_labels": budget if name == "labeled_student" else 0,
                }
            selected = [queries["ids"][int(i)] for i in chosen]
            results.append(
                {"seed": seed, "budget": budget, "query_selection_sha256": sha(canonical(selected)), "arms": arms}
            )
            if observe is not None:
                observe(
                    {
                        "seed": seed,
                        "budget": budget,
                        "ids": list(held["ids"]),
                        "labels": held["labels"].tolist(),
                        "query_ids": selected,
                        "predictions": {n: p.tolist() for n, p in preds.items()},
                    }
                )
    return {
        "schema": "quantfit-head-benchmark/v1",
        "reference": "compiled_adapted",
        "archive_cases": len(ar),
        "held_out_cases": len(held["ids"]),
        "held_out_ids_sha256": sha(canonical(held["ids"])),
        "archive_logit_rows_materialized": len(ar),
        "target_logit_rows_materialized": len(target_cache),
        "trials": results,
    }
