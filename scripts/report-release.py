"""Save public build results without credentials or unbounded build logs."""
import json
import os
from pathlib import Path
import re

report = {
    'tag': os.environ['GITHUB_REF_NAME'],
    'source_commit': os.environ['GITHUB_SHA'],
    'windows': os.environ['WINDOWS_RESULT'],
    'publish': os.environ['PUBLISH_RESULT'],
    'run_url': f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
}
report['release_url'] = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/releases/tag/{report['tag']}"
if report['windows'] != 'success':
    messages = []
    for path in Path('.local/release-diagnostics').glob('*.log'):
        lines = path.read_text(errors='replace').splitlines()
        indices = [i for i, line in enumerate(lines) if re.search(r'FAILED|FAILURES|Error:|Exception:|AssertionError|Tests failed|error:', line)]
        selected = sorted({j for i in indices for j in range(max(0, i-2), min(len(lines), i+10))})
        messages.append('\n'.join(lines[i] for i in selected)[-18000:])
    details = '\n'.join(messages)
    for name, value in os.environ.items():
        if len(value) > 8 and any(word in name.upper() for word in ('TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')):
            details = details.replace(value, '[redacted]')
    report['diagnostics'] = re.sub(r'(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)', '[redacted]', details)
Path('target/release-status.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
