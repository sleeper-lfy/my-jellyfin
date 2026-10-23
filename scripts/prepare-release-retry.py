"""Only reuse a successful Windows build when all application inputs match its tag."""
import json
import os
from pathlib import Path
import subprocess
import tomllib

request = json.loads(Path('scripts/release-request.json').read_text())
version = tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
tag = request['tag']
assert tag == 'v' + version
subprocess.run(['git', 'fetch', '--depth=1', 'origin', f'refs/tags/{tag}:refs/tags/{tag}'], check=True)
source = subprocess.check_output(['git', 'rev-parse', tag + '^{}'], text=True).strip()
assert source == request['source_commit']
inputs = ['src', 'android', 'assets', 'plugins', 'installer', 'requirements.lock', 'pyproject.toml',
          'scripts/build-windows.ps1', 'scripts/build-installer-windows.ps1', 'scripts/fetch-mpv-windows.ps1',
          'scripts/launcher.py', 'scripts/verify-package.py', 'scripts/verify-installer-windows.ps1']
subprocess.run(['git', 'diff', '--exit-code', source, '--', *inputs], check=True)
run_id = int(request['windows_run_id'])
repository = os.environ['GH_REPO']
run = json.loads(subprocess.check_output(['gh', 'api', f'repos/{repository}/actions/runs/{run_id}'], text=True))
assert run['head_sha'] == source
jobs = json.loads(subprocess.check_output(['gh', 'api', f'repos/{repository}/actions/runs/{run_id}/jobs'], text=True))
assert any(job['name'] == 'windows' and job['conclusion'] == 'success' for job in jobs['jobs'])
with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
    output.write(f'tag={tag}\nsource_commit={source}\nwindows_run_id={run_id}\n')
print('Verified unchanged application inputs and successful Windows build:', source, run_id)
