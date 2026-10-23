"""Record package-only CI outcome; never create or update a GitHub Release."""
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

request = json.loads(Path('scripts/package-request.json').read_text())
report = {
    'version': request['version'],
    'source_commit': request['source_commit'],
    'workflow_commit': os.environ['GITHUB_SHA'],
    'windows': os.environ['WINDOWS_RESULT'],
    'delivery': os.environ['DELIVERY_RESULT'],
    'release_published': False,
    'run_url': f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
}
results = Path('.local/package-diagnostics/test-results.xml')
if results.is_file():
    root = ET.parse(results).getroot()
    report['tests'] = {key: sum(int(suite.get(key, 0)) for suite in root.iter('testsuite'))
                       for key in ('tests', 'failures', 'errors', 'skipped')}
if report['windows'] != 'success' or report['delivery'] != 'success':
    messages = []
    for path in Path('.local/package-diagnostics').glob('*.log'):
        lines = path.read_text(errors='replace').splitlines()
        indices = [i for i, line in enumerate(lines) if re.search(r'FAILED|FAILURES|Error:|Exception:|AssertionError|Tests failed|error:', line)]
        selected = sorted({j for i in indices for j in range(max(0, i-2), min(len(lines), i+10))})
        messages.append('\n'.join(lines[i] for i in selected)[-18000:])
    details = '\n'.join(messages)
    for name, value in os.environ.items():
        if len(value) > 8 and any(word in name.upper() for word in ('TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')):
            details = details.replace(value, '[redacted]')
    report['diagnostics'] = re.sub(r'(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)', '[redacted]', details)
Path('target/package-status.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
