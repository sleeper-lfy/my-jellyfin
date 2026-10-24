"""Recover artifact delivery only when the original Windows build already succeeded."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET


def gh(*args):return subprocess.check_output(['gh',*args],text=True)


def main():
    request=json.loads(Path('scripts/recover-package-request.json').read_text())
    assert request['recover'] is True
    source=request['source_commit'];run_id=int(request['package_run_id']);repo=os.environ['GH_REPO']
    assert re.fullmatch('[0-9a-f]{40}',source)
    version=tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
    run=json.loads(gh('api',f'repos/{repo}/actions/runs/{run_id}'))
    assert run['path'].split('@')[0]=='.github/workflows/package-current.yml'
    assert run['conclusion']=='failure'
    jobs=json.loads(gh('api',f'repos/{repo}/actions/runs/{run_id}/jobs'))['jobs']
    assert any(j['name']=='windows' and j['conclusion']=='success' for j in jobs)
    assert any(j['name']=='deliver' and j['conclusion']=='failure' for j in jobs)
    head=run['head_sha'];assert re.fullmatch('[0-9a-f]{40}',head)
    for revision in (head,source):subprocess.run(['git','fetch','--depth=1','origin',revision],check=True)
    original=json.loads(subprocess.check_output(['git','show',head+':scripts/package-request.json'],text=True))
    assert original['source_commit']==source and original['version']==version and original['package'] is True
    spec=importlib.util.spec_from_file_location('publisher','scripts/publish-package-release.py');publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
    subprocess.run(['git','diff','--exit-code',source,'--',*publisher.INPUTS],check=True)
    subprocess.run([sys.executable,'scripts/verify-android-target.py'],check=True)
    android=json.loads(Path('target/android-build.json').read_text());assert android['source_commit']==source and android['version']==version
    directory=Path('.local/recovered-package');directory.mkdir(parents=True,exist_ok=True)
    diagnostics=Path('.local/recovered-diagnostics');diagnostics.mkdir(parents=True,exist_ok=True)
    gh('run','download',str(run_id),'--repo',repo,'--name','Lumen-windows-x64','--dir',str(directory))
    gh('run','download',str(run_id),'--repo',repo,'--name','package-diagnostics','--dir',str(diagnostics))
    suites=ET.parse(diagnostics/'test-results.xml').getroot()
    counts={key:sum(int(s.get(key,0)) for s in suites.iter('testsuite')) for key in ('tests','errors','failures','skipped')}
    assert counts['tests']>0 and counts['errors']==counts['failures']==counts['skipped']==0
    executable=next(directory.rglob('Lumen-Setup-x64.exe'));checksum=Path(str(executable)+'.sha256')
    assert hashlib.sha256(executable.read_bytes()).hexdigest()==checksum.read_text(encoding='utf-8-sig').split()[0].lower()
    subprocess.run([sys.executable,'scripts/package-installer-target.py',str(executable),'target','--revision',source],check=True)
    result={'version':version,'source_commit':source,'workflow_commit':head,'windows':'success','delivery':'success','release_published':False,'run_url':f'https://github.com/{repo}/actions/runs/{run_id}','tests':counts,
            'recovery':{'original_run_id':run_id,'recovery_run_id':int(os.environ['GITHUB_RUN_ID']),'run_url':f'https://github.com/{repo}/actions/runs/{os.environ["GITHUB_RUN_ID"]}','reason':'Original Windows job succeeded; final Git delivery failed'}}
    Path('target/package-status.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Recovered original verified installer without rebuilding:',counts,source)


if __name__=='__main__':main()
