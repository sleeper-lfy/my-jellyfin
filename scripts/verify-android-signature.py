"""Locate apksigner using Python, then verify the delivered APK and certificate."""
import json
import os
from pathlib import Path
import re
import subprocess

sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
tools = list((sdk / 'build-tools').glob('*/apksigner'))
assert tools, f'apksigner is missing from {sdk / "build-tools"}'
signer = max(tools, key=lambda path: tuple(map(int, re.findall(r'\d+', path.parent.name))))
result = subprocess.run([str(signer), 'verify', '--verbose', '--print-certs', 'target/Lumen-android-debug.apk'],
                        check=True, text=True, capture_output=True)
print(result.stdout)
expected = json.loads(Path('target/android-build.json').read_text())['signing_certificate_sha256']
actual = re.search(r'Signer #1 certificate SHA-256 digest: (\w+)', result.stdout)
assert actual and actual.group(1) == expected, 'APK signing certificate differs from the build record'
