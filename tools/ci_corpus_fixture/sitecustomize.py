"""Explicit CI-only native source/generation seams; never an installed plugin.

The actual loader, verifier, report writer, policies, receivers and CLI execute.
No Hub, model, judge or physical inference is observed by this fixture.
"""

import hashlib
import json
import os
import platform
from pathlib import Path

if os.environ.get("QUANTFIT_CORPUS_CI") == "1":
    import datasets

    from quantfit.safety import report
    from quantfit.safety import verify as v
    from quantfit.safety.report import ArmRun

    def event(kind, **facts):
        if os.environ.get("QUANTFIT_CORPUS_CI_LOG"):
            with Path(os.environ["QUANTFIT_CORPUS_CI_LOG"]).open("a", encoding="utf-8") as out:
                out.write(json.dumps({"event": kind, **facts}) + "\n")

    class Builder:
        def __init__(self, revision):
            self.hash = revision

        def as_streaming_dataset(self, split):
            event("stream")

            def generate():
                for i in range(int(os.environ.get("QUANTFIT_CORPUS_CI_N", "30"))):
                    event("row")
                    yield {
                        "prompt": f"controlled benign placeholder {i}",
                        "zone": ("clear_safe", "clear_unsafe", "borderline")[i % 3],
                        "expected": "unsafe" if i % 2 == 0 else "safe",
                    }

            return datasets.IterableDataset.from_generator(generate)

    def builder(path, *, revision, token):
        event("builder")
        return Builder(revision)

    def generate(model, prompts, max_new_tokens, token):
        if os.environ.get("QUANTFIT_LOCAL_CORPUS_CI") == "1":
            event(
                "arm",
                n=len(prompts),
                ordered_sha256=hashlib.sha256(
                    json.dumps(prompts, ensure_ascii=False, separators=(",", ":")).encode()
                ).hexdigest(),
            )
        else:
            event("arm", n=len(prompts))
        case = int(os.environ.get("QUANTFIT_CORPUS_CI_CASE", "0"))
        baseline = "base" in model
        labels = [(i % 2 == 0) for i in range(len(prompts))]
        if case == 4:
            labels = [False] * len(prompts)
        elif case == 3 and not baseline:
            labels[0] = False
        values = ["refused" if flag else "answered" for flag in labels]
        return values, ArmRun(
            model,
            ("a" if baseline else "b") * 40,
            "torch.float32",
            0.0,
            {"name": "transformers", "version": "synthetic-not-used", "device": "cpu"},
            None,
        )

    datasets.load_dataset_builder = builder
    v._generate_completions = generate
    v._classify_refusals = lambda values, token: ([x == "refused" for x in values], 0.0)
    report.environment_fingerprint = lambda: {
        "python": platform.python_version(),
        "torch": "synthetic-not-used",
        "transformers": "synthetic-not-used",
        "cuda": None,
        "device": "cpu",
    }

    if os.environ.get("QUANTFIT_LOCAL_CORPUS_CI") == "1":
        from quantfit.safety import retention_io

        original_hold = retention_io.hold

        def held_file(path, limit):
            if Path(path).resolve() == Path(os.environ["QUANTFIT_LOCAL_CORPUS_PATH"]).resolve():
                event("local_read")
            return original_hold(path, limit)

        def forbidden_builder(*args, **kwargs):
            event("forbidden_hub")
            raise AssertionError("controlled local source must not invoke the Hub builder")

        def local_judge(values, token):
            event("judge", n=len(values))
            return [x == "refused" for x in values], 0.0

        retention_io.hold = held_file
        datasets.load_dataset_builder = forbidden_builder
        v._classify_refusals = local_judge


if judge_events := os.environ.get("QUANTFIT_JUDGE_OBSERVATION_CI"):
    import quantfit
    from quantfit.safety import verify as judge_verify

    def fixture_judge(values, token):
        expected = [
            f"PRIVATE_TWO_JUDGE_CONTENT_DO_NOT_REFLECT {arm} {index % 2}"
            for arm in ("baseline", "quantized")
            for index in range(8)
        ]
        assert values == expected and token is None
        assert str(Path(quantfit.__file__).resolve()) == os.environ["QUANTFIT_JUDGE_OBSERVATION_ORIGIN"]
        with Path(judge_events).open("a", encoding="utf-8") as log:
            log.write(json.dumps({"classifier_calls": 1, "rows": len(values), "origin_matched": True}) + "\n")
        return [
            True,
            True,
            False,
            False,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
            True,
            True,
            False,
        ], 0.25

    def no_generation(*args, **kwargs):
        raise AssertionError("held-judge fixture must not generate completions or load a corpus")

    judge_verify._classify_refusals = fixture_judge
    judge_verify._generate_completions = no_generation
    judge_verify._load_probes = no_generation
