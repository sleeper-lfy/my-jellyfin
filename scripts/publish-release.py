"""Publish a tagged release only after both installer files have been verified."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tomllib

version = tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
tag = os.environ['GITHUB_REF_NAME']
assert tag == 'v' + version
revision = os.environ['SOURCE_COMMIT']
windows = Path('.local/release-windows/Lumen-Setup-x64.exe')
android = Path('target/Lumen-android-debug.apk')
for archive in (windows, android):
    checksum = Path(str(archive) + '.sha256')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == checksum.read_text().split()[0], archive
    assert archive.stat().st_size > 1024 * 1024, archive
notes = Path('.local/release-notes.md')
notes.write_text(Path(f'docs/releases/{version}.md').read_text() + f'\n源码提交：`{revision}`\n', encoding='utf-8')
assets = [str(p) for archive in (windows, android) for p in (archive, Path(str(archive) + '.sha256'))]
view = subprocess.run(['gh', 'release', 'view', tag, '--json', 'isDraft,targetCommitish'], capture_output=True, text=True)
if view.returncode:
    subprocess.run(['gh', 'release', 'create', tag, '--verify-tag', '--draft', '--target', revision,
                    '--title', f'Lumen {version} · Windows + Android', '--notes-file', str(notes)], check=True)
else:
    # Never repurpose a release that belongs to another revision.
    existing = json.loads(view.stdout)
    assert existing['targetCommitish'] == revision, existing
subprocess.run(['gh', 'release', 'upload', tag, *assets, '--clobber'], check=True)
metadata = json.loads(subprocess.check_output(['gh', 'release', 'view', tag, '--json', 'assets'], text=True))
sizes = {asset['name']: asset['size'] for asset in metadata['assets']}
for asset in assets:
    assert sizes.get(Path(asset).name) == Path(asset).stat().st_size, asset
subprocess.run(['gh', 'release', 'edit', tag, '--draft=false', '--latest', '--notes-file', str(notes)], check=True)
published = json.loads(subprocess.check_output(['gh', 'release', 'view', tag, '--json', 'isDraft,url'], text=True))
assert not published['isDraft'], published
print('Published both verified installers:', published['url'])
