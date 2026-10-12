import hashlib
import json
import subprocess
from pathlib import Path
from xml.etree import ElementTree

checkout = Path(r'C:\tmp\qf-release-0.16.0-20261008')
output = checkout / 'validation/2026-10-09-cli-readme'
python = str(checkout / 'tools/ci/.venv/Scripts/python.exe')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
assert head == '97d79d6b7c9511b308c8211bbb9356813d46892d'
Path(r'C:\tmp\qf-readme-draft-20261009\README.md').write_bytes((checkout / 'README.md').read_bytes())
commands = [
    ('supported-properties', [python, '-m', 'pytest', 'tests/test_numerical_properties.py::test_rejection_threshold_is_minimal_and_controls_size', 'tests/test_numerical_properties.py::test_wilson_interval_contains_estimate_and_is_complement_symmetric', '-q', f'--junitxml={output / "supported-properties.xml"}']),
    ('final-docs-tests', [python, '-m', 'pytest', 'tests/test_quickstart.py', 'tests/test_audit.py', '-q', f'--junitxml={output / "final-docs-tests.xml"}']),
    ('final-lint', [python, '-m', 'ruff', 'check', 'quantfit', 'tests', 'tools']),
    ('final-format', [python, '-m', 'ruff', 'format', '--check', 'quantfit', 'tests', *[p.as_posix() for p in Path(checkout / 'tools').glob('ci_*.py')], 'tools/ci_gate_fixture']),
    ('final-mypy', [python, '-m', 'mypy', '--strict', 'quantfit/spec.py', 'quantfit/engines/base.py']),
    ('final-audit', [python, '-m', 'quantfit.cli', 'audit', '--json']),
    ('final-quickstart-syntax', [python, 'tools/quickstart_check.py', '--readme', 'README.md', '--quantfit-bin', python.replace('\\', '/') + ' -m quantfit.cli', '--no-run', '--min-commands', '20', '--json', str(output / 'final-quickstart-syntax.json')]),
    ('fenced-parser', [python, r'C:\tmp\qf-readme-draft-20261009\parse-fenced-examples.py']),
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
assert subprocess.check_output(['git', 'diff', '9d59739645e5c0021aec8288b480ed2e9c5bea30', head, '--', 'quantfit', 'tests', 'tools', '.github'], cwd=checkout) == b''
receipt = {'qualified_source_head': head, 'reviewed_source_package_base': '9d59739645e5c0021aec8288b480ed2e9c5bea30', 'implementation_unchanged_from_hosted_qualified_feature': True, 'scope': 'README-only fixes; full local available suite at ad95062, then final affected documentation tests/audit/parser and supported numerical properties at 97d79d6. Sparse local environment deliberately lacks Torch; full installed/runtime/numerical gates run on hosted CI. No local model downloads/new dependencies/worktrees.', 'initial_environment_failure_receipt': 'local-gates.json', 'initial_environment_failure': 'Root mistakenly included Torch-only RTN property in sparse environment. Original properties.xml/log retain 2 pass and 1 ModuleNotFoundError failure; no product/test change or tolerance weakening.', 'gates': results, 'readme_sha256': hashlib.sha256((checkout / 'README.md').read_bytes()).hexdigest(), 'full_available_unit_at_ad95062': counts(output / 'unit.xml'), 'supported_properties': counts(output / 'supported-properties.xml'), 'final_affected_docs_tests': counts(output / 'final-docs-tests.xml'), 'hosted_final_head': 'PENDING'}
(output / 'final-local-gates.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
raise SystemExit(any(r['exit'] for r in results) or len(results) != len(commands))
