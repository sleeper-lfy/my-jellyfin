"""Exercise the packaged executable and isolated worker, without relying on console output."""
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile

executable = Path(sys.argv[1]).resolve(strict=True)
with tempfile.TemporaryDirectory(prefix='lumen-package-') as directory:
    root = Path(directory)
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    subprocess.run([str(executable),'--smoke','--data-dir',str(root/'data')],check=True,timeout=60,env=environment)
    assert (root/'data/smoke.png').stat().st_size > 1000
    if sys.platform == 'win32':
        subprocess.run([str(executable),'--verify-mpv','--data-dir',str(root/'mpv')],check=True,timeout=30,env=environment)
        assert json.loads((root/'mpv/mpv-check.json').read_text(encoding='utf-8'))['shader']
    source, target = root/'input.json', root/'output.json'
    source.write_text(json.dumps({'script':'function test(x){return {result:x.a+x.b,filesystem:typeof require};}',
                                 'function':'test','argument':{'a':2,'b':3}}),encoding='utf-8')
    subprocess.run([str(executable),'--plugin-worker',str(source),str(target)],check=True,timeout=15,env=environment)
    assert json.loads(target.read_text(encoding='utf-8'))['result']=={'result':5,'filesystem':'undefined'}
print('Packaged UI and isolated plugin worker passed.')
