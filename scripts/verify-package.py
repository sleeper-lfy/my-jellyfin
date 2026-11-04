"""Exercise the packaged executable and isolated worker, without relying on console output."""
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread

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
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/plain');self.end_headers();self.wfile.write(b'compat-worker-ok')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        body=root/'http-body';source.write_text(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/test','headers':{},'proxy':'','maximum':1000}),encoding='utf-8')
        subprocess.run([str(executable),'--browser-http-worker',str(source),str(target),str(body)],check=True,timeout=30,env=environment)
        assert json.loads(target.read_text(encoding='utf-8'))['status']==200
        assert body.read_bytes()==b'compat-worker-ok'
    finally:server.shutdown();server.server_close();thread.join(2)
print('Packaged UI and isolated plugin worker passed.')
