# Held judge observation and offline comparison

This 0.56.0 source/editable check used eight fictional pairs, the native
report/capture/key and label writers, and a controlled classifier. The real OS
CLI made one complete 16-cell call. Baseline came first, with pair indices
ascending in each arm. The comparison ran independently on the full sheet and
on the native retained labels. Both received identical native per-arm counts.
An incorrect observation SHA and an output alias refused with exit 2 and left
the original inputs intact.

Reproduce from the checkout with its test dependencies and use fresh destinations.

```bash
python -B -X utf8 tools/ci_judge_observation.py --work ./new-private-judge-work --record ./new-judge-functional.json
```

[functional.json](functional.json) records the exact source-byte hashes, five
CLI outcomes and aggregate tables. The producer verifies that its source inputs
remain identical after execution. The private work directory contains fixture
inputs, an observation and CLI outputs. Keep it out of Git. The committed
record omits individual cells, flags, labels and completion text.

The controlled classifier supplied flags. The run does not establish real model
inference, hardware behavior, human truth, judge execution authenticity,
independence, sensitivity, gate eligibility or scientific GO. Hosted installed
wheel and rebuilt-sdist profiles are separate checks.
