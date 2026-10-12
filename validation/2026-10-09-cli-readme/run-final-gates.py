import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

checkout = Path(r'C:\tmp\qf-release-0.16.0-20261008')
output = checkout / 'validation/2026-10-09-cli-readme'
output.mkdir(parents=True, exist_ok=True)
python = str(checkout / 'tools/ci/.venv/Scripts/python.exe')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
assert head == 'ad95062b23fc189769e463c48a71daadd709079f'
commands = [
    ('unit', [python, '-m', 'pytest', 'tests', '-q', '--ignore=tests/test_numerical_properties.py', f'--junitxml={output / "unit.xml"}']),
    ('properties', [python, '-m', 'pytest', 'tests/test_numerical_properties.py', '-q', f'--junitxml={output / "properties.xml"}']),
    ('lint', [python, '-m', 'ruff', 'check', 'quantfit', 'tests', 'tools']),
    ('format', [python, '-m', 'ruff', 'format', '--check', 'quantfit', 'tests', *[p.as_posix() for p in Path(checkout / 'tools').glob('ci_*.py')], 'tools/ci_gate_fixture']),
    ('mypy', [python, '-m', 'mypy', '--strict', 'quantfit/spec.py', 'quantfit/engines/base.py']),
    ('audit', [python, '-m', 'quantfit.cli', 'audit', '--json']),
    ('quickstart-syntax', [python, 'tools/quickstart_check.py', '--readme', 'README.md', '--quantfit-bin', python.replace('\\', '/') + ' -m quantfit.cli', '--no-run', '--min-commands', '20', '--json', str(output / 'quickstart-syntax.json')]),
]
results = []
for name, command in commands:
    with (output / f'{name}.log').open('wb') as log:
        result = subprocess.run(command, cwd=checkout, stdout=log, stderr=subprocess.STDOUT, check=False)
    results.append({'name': name, 'argv': command, 'exit': result.returncode})
    print(json.dumps({'gate': name, 'exit': result.returncode}), flush=True)
    if result.returncode:
        print((output / f'{name}.log').read_text(encoding='utf-8', errors='replace')[-5000:], flush=True)
        break
def counts(path):
    cases = ElementTree.parse(path).getroot().findall('.//testcase')
    values = {'cases': len(cases), 'skipped': sum(c.find('skipped') is not None for c in cases), 'failed': sum(c.find('failure') is not None for c in cases), 'errors': sum(c.find('error') is not None for c in cases)}
    values['passed'] = values['cases'] - values['skipped'] - values['failed'] - values['errors']
    return values
receipt = {'qualified_source_head': head, 'platform': platform.platform(), 'python': platform.python_version(), 'scope': 'Documentation change. Reused sparse local CI environment; numerical/model-heavy Torch coverage and actual installed clean-runtime README execution are hosted gates, not this local syntax check. No local models/new dependencies/worktrees/containers.', 'gates': results, 'readme_sha256': hashlib.sha256((checkout / 'README.md').read_bytes()).hexdigest(), 'unit': counts(output / 'unit.xml'), 'properties': counts(output / 'properties.xml') if (output / 'properties.xml').exists() else None, 'hosted_final_head': 'PENDING', 'raw_payloads': False}
(output / 'local-gates.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
raise SystemExit(any(r['exit'] for r in results) or len(results) != len(commands))
