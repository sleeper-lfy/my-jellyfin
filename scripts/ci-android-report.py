"""Record a bounded, redacted CI failure summary for remote troubleshooting."""
from pathlib import Path
import json
import os
import re

secrets=[value for name,value in os.environ.items() if len(value)>8 and any(word in name for word in ('TOKEN','SECRET','PASSWORD','CREDENTIAL'))]
def tail(name):
    path=Path(name)
    if not path.exists():return []
    lines=path.read_text(errors='replace').splitlines()
    selected=[line for line in lines if re.search(r'error:|FAILURE:|What went wrong|Exception|failed|Could not|not found|requires|SDK location|> ',line,re.I)]
    text='\n'.join(selected[-45:] if selected else lines[-25:])[-12000:]
    for secret in secrets:text=text.replace(secret,'[redacted]')
    text=re.sub(r'(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)','[redacted]',text)
    return text.splitlines()
report={'source_commit':os.environ.get('SOURCE_COMMIT'),
        'run':os.environ.get('GITHUB_SERVER_URL','https://github.com')+'/'+os.environ.get('GITHUB_REPOSITORY','')+'/actions/runs/'+os.environ.get('GITHUB_RUN_ID',''),
        'sdk_outcome':os.environ.get('SDK_OUTCOME'),'build_outcome':os.environ.get('BUILD_OUTCOME'),
        'sdk':tail('android-sdk.log'),'build':tail('android-build.log')}
Path('target').mkdir(exist_ok=True)
Path('target/android-ci-failure.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
