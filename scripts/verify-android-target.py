"""Verify the committed, tested APK matches its source tree and checksum."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'target/android-build.json').read_text())
archive=root/'target/Lumen-android-debug.apk'
assert archive.stat().st_size==manifest['bytes'], 'APK size mismatch'
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
assert digest==manifest['sha256'], 'APK hash mismatch'
assert digest==(archive.with_suffix('.apk.sha256')).read_text().split()[0]
source=hashlib.sha256()
files=subprocess.check_output(['git','ls-files','-z','android'],cwd=root).split(b'\0')
for path in sorted(path for path in files if path):
    source.update(path+b'\0');source.update((root/path.decode()).read_bytes())
assert source.hexdigest()==manifest['source_sha256'], 'Android source changed; rebuild and verify target APK first'
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    assert {'AndroidManifest.xml','classes.dex'}<=set(package.namelist())
print('Verified target APK, checksum, ZIP contents and matching Android source')
