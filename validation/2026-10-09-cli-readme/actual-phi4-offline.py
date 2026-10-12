import hashlib
import json
import subprocess
from pathlib import Path

checkout = Path(r'C:\tmp\qf-release-0.16.0-20261008')
source = Path(r'C:\tmp\qf-next-pr-receipts-20261008\hosted-reference-campaign-37890682118')
target = Path(r'C:\tmp\qf-readme-draft-20261009\actual-phi4-offline-final')
target.mkdir(exist_ok=True)
prefix = [str(checkout / 'tools/ci/.venv/Scripts/python.exe'), '-m', 'quantfit.cli']
report = source / 'run-1/report.json'
native = json.loads((source / 'native-cold-run.json').read_bytes())
original_t0 = (source / 'native-t0.json').read_bytes()
commands = [
    ['emit', 'model-card', '--report', str(report)],
    ['bundle', 'create', '--report', str(report), '--out', str(target / 'evidence'), '--json'],
    ['bundle', 'verify', '--bundle', str(target / 'evidence'), '--json'],
    ['t0', '--reports', *[str(source / f'run-{i}/report.json') for i in (1, 2, 3)], '--out', str(target / 'relocated-t0.json'), '--json'],
    ['references', 'list', '--json'],
]
results = []
for i, argv in enumerate(commands):
    result = subprocess.run(prefix + argv, cwd=checkout, capture_output=True, check=False)
    (target / f'{i}-stdout.txt').write_bytes(result.stdout)
    (target / f'{i}-stderr.txt').write_bytes(result.stderr)
    results.append({'argv': prefix + argv, 'exit': result.returncode})
assert all(result['exit'] == 0 for result in results)
assert native['runs'][0]['native_exit_code'] == 3
copied = json.loads((target / 'evidence/report.json').read_bytes())
assert copied['drift']['regression_detected'] is True
assert (source / 'native-t0.json').read_bytes() == original_t0
relocated = json.loads((target / 'relocated-t0.json').read_bytes())
assert relocated['protocol_pass'] is True
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
assert head == 'ad95062b23fc189769e463c48a71daadd709079f'
receipt = {'qualified_source_head': head, 'scope': 'Existing actual hosted Phi4 aggregates, local editable CLI consumers only; no new model/network/calibration/human labels. Native regression exit3 preserved; consumer exit0 is card/bundle integrity or T0 agreement.', 'committed_source_report': 'validation/2026-10-09-phi4-public-candidate/producer/run-1/report.json', 'source_report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(), 'native_source_exit': 3, 'producer_t0_original_sha256': hashlib.sha256(original_t0).hexdigest(), 'steps': results, 'all_zero': True, 'relocated_t0_protocol_pass': True}
(target / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'consumer_steps': len(results), 'all_zero': True, 'native_regression_preserved': 3}))
