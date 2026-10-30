"""Publish a tagged release only after both installer files have been verified."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

version = tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
tag = os.environ.get('RELEASE_TAG') or os.environ['GITHUB_REF_NAME']
assert tag == 'v' + version
revision = os.environ['SOURCE_COMMIT']
assert subprocess.check_output(['git', 'rev-parse', tag + '^{}'], text=True).strip() == revision
windows = Path('.local/release-windows/Lumen-Setup-x64.exe')
android = Path('target/Lumen-android-debug.apk')
# Human checks are bound to the exact installer, independently of CI success.
sys.path.insert(0, str(Path('src').resolve()))
from lumen.release_acceptance import validate, source_state
acceptance_path = Path('docs/validation/windows-release-acceptance.json')
acceptance = json.loads(acceptance_path.read_text(encoding='utf-8-sig'))
validate(acceptance, windows, require_release=True)
assert acceptance['version'] == version, 'Acceptance version mismatch'
assert acceptance['source']['content_sha256'] == source_state(Path.cwd())['content_sha256'], 'Acceptance source mismatch'
for archive in (windows, android):
    checksum = Path(str(archive) + '.sha256')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == checksum.read_text(encoding='utf-8-sig').split()[0].lower(), archive
    assert archive.stat().st_size > 1024 * 1024, archive
notes = Path('.local/release-notes.md')
provenance=f'\n发布标签提交：`{revision}`\n安装包构建源码：`{os.environ["BUILD_SOURCE_COMMIT"]}`（已核对应用及构建输入一致）。\n' if os.environ.get('BUILD_SOURCE_COMMIT') else f'\n源码提交：`{revision}`\n'
notes.write_text(Path(f'docs/releases/{version}.md').read_text() + provenance, encoding='utf-8')
assets = [str(p) for archive in (windows, android) for p in (archive, Path(str(archive) + '.sha256'))]
view = subprocess.run(['gh', 'release', 'view', tag, '--json', 'isDraft,targetCommitish'], capture_output=True, text=True)
if view.returncode:
    # The tag is already verified above. Do not request creation of a tag at an
    # older workflow revision: GITHUB_TOKEN cannot perform that workflows write.
    subprocess.run(['gh', 'release', 'create', tag, '--verify-tag', '--draft',
                    '--title', f'Lumen {version} · Windows + Android', '--notes-file', str(notes)], check=True)
else:
    # The immutable tag target was checked above; targetCommitish can be the
    # default branch because the API ignores it for an existing tag.
    existing = json.loads(view.stdout)
    assert not existing['isDraft'] or existing['targetCommitish'], existing
subprocess.run(['gh', 'release', 'upload', tag, *assets, '--clobber'], check=True)
metadata = json.loads(subprocess.check_output(['gh', 'release', 'view', tag, '--json', 'assets'], text=True))
sizes = {asset['name']: asset['size'] for asset in metadata['assets']}
for asset in assets:
    assert sizes.get(Path(asset).name) == Path(asset).stat().st_size, asset
subprocess.run(['gh', 'release', 'edit', tag, '--draft=false', '--latest', '--notes-file', str(notes)], check=True)
published = json.loads(subprocess.check_output(['gh', 'release', 'view', tag, '--json', 'isDraft,publishedAt,tagName,url'], text=True))
assert not published['isDraft'] and published['publishedAt'] and published['tagName'] == tag, published
print('Published both verified installers:', published['url'])
