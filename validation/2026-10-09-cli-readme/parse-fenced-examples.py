import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path

from quantfit.cli import _build_parser

checkout = Path(r'C:\tmp\qf-release-0.16.0-20261008')
readme = Path(r'C:\tmp\qf-readme-draft-20261009\README.md')
spec = importlib.util.spec_from_file_location('quickstart', checkout / 'tools/quickstart_check.py')
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)
results = []
for command in module.extract_commands(readme.read_text(encoding='utf-8'), include_inline=False):
    if command.argv[0] != 'quantfit':
        continue
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            _build_parser().parse_args(command.argv[1:])
        status = 0
    except SystemExit as exc:
        status = exc.code
    results.append({'line': command.line, 'argv': command.argv, 'parser_exit': status, 'output': output.getvalue()})
receipt = {'readme_sha256': hashlib.sha256(readme.read_bytes()).hexdigest(), 'scope': 'Full argparse parsing of fenced quantfit examples only; no command callbacks/models/network. Inline bare command names are excluded.', 'parsed': len(results), 'failures': [r for r in results if r['parser_exit'] != 0], 'examples': results}
(readme.parent / 'fenced-parser.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'parsed': len(results), 'failures': receipt['failures']}))
raise SystemExit(bool(receipt['failures']))
