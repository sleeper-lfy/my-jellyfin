"""Measure the actual Qt-free desktop owner, including IPC/logging and LAN images.

Linux /proc evidence only. Does not build a package or claim Windows working-set
acceptance. Uses a temporary synthetic library and exits its own background owner.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler
import zlib


def memory(pid):
    data = {}
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('VmRSS', 'VmHWM'):
            data[key + '_bytes'] = int(value.split()[0]) * 1024
    maps = Path(f'/proc/{pid}/maps').read_text()
    data['qt_mapped'] = 'libQt6' in maps
    data['mpv_mapped'] = 'libmpv' in maps
    data['rss_mib'] = round(data['VmRSS_bytes'] / 1048576, 3)
    children = Path(f'/proc/{pid}/task/{pid}/children')
    data['direct_child_pids'] = [int(item) for item in children.read_text().split()] if children.exists() else None
    return data


def profile():
    if not sys.platform.startswith('linux'):
        raise SystemExit('Requires Linux /proc; use Windows measurements for Windows acceptance.')
    from lumen.core import Library
    from lumen.desktop_runtime import RuntimeClient
    root = Path(__file__).resolve().parents[1]
    samples = []
    with tempfile.TemporaryDirectory(prefix='lumen-desktop-owner-') as temporary:
        directory = Path(temporary) / 'data'
        library = Library(directory)
        cache = directory / 'cache'; cache.mkdir(exist_ok=True)
        def chunk(kind, data):
            return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
        # Tiny valid 2:3 RGB poster: no image/Qt imports in the probe itself.
        poster = cache / 'synthetic.png'
        poster.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 2, 3, 8, 2, 0, 0, 0)) +
                           chunk(b'IDAT', zlib.compress((b'\0' + b'\x20\x80\xa0' * 2) * 3)) + chunk(b'IEND', b''))
        with library.db:
            identifier = library.db.execute('INSERT INTO works(identity,kind,title,added,metadata,thumbnail) VALUES(?,?,?,?,?,?)',
                ('owner-fixture', 'movie', 'Synthetic', '2026-11-11', '{"nfo_poster":true}', str(poster))).lastrowid
        library.set_setting('lan', {'enabled': True, 'port': 0})
        library.set_setting('lan_token', 'synthetic-profile-token')
        library.close()
        environment = dict(os.environ, PYTHONPATH=str(root / 'src'))
        process = subprocess.Popen([sys.executable, '-m', 'lumen', '--background', '--data-dir', str(directory)],
                                   env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        client = None
        endpoints = []
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(process.communicate()[1].decode()[-2000:])
                try:
                    client = RuntimeClient(directory, timeout=2)
                    state = client.request('status')
                    break
                except (OSError, ValueError): time.sleep(.05)
            else: raise RuntimeError('Desktop owner did not start')
            samples.append({'stage': 'actual_application_background_entry', **memory(process.pid)})
            opener = build_opener(ProxyHandler({}))
            for route in ('/api/info', '/api/works', f'/api/works/{identifier}/cover'):
                request = Request(f'http://127.0.0.1:{state["lan"]["port"]}' + route,
                                  headers={'Authorization': 'Bearer synthetic-profile-token'})
                with opener.open(request, timeout=20) as response:
                    endpoints.append({'route': route, 'http': response.status, 'bytes': len(response.read())})
            time.sleep(.3)
            samples.append({'stage': 'after_api_and_isolated_poster_request', **memory(process.pid)})
            for _ in range(10):
                client.request('status'); time.sleep(.2)
            samples.append({'stage': 'idle_after_repeated_control_requests', **memory(process.pid)})
            if any(item['qt_mapped'] or item['mpv_mapped'] for item in samples):
                raise RuntimeError('Desktop owner loaded GUI/playback libraries')
            client.request('exit')
            _, error = process.communicate(timeout=15)
            if process.returncode: raise RuntimeError(error.decode()[-2000:])
        finally:
            if process.poll() is None:
                try:
                    if client: client.request('exit')
                    process.communicate(timeout=10)
                except Exception:
                    process.kill(); process.communicate()
    return {'platform': 'Linux', 'verified_at': datetime.now(timezone.utc).isoformat(),
            'entry': 'python -m lumen --background --data-dir <temporary synthetic library>',
            'samples': samples, 'endpoints': endpoints,
            'source_sha256': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [root / 'src/lumen' / name for name in
                                           ('app.py', 'desktop_runtime.py', 'background_service.py', 'image_isolation.py', 'logging_setup.py')]},
            'limitations': ['Linux resident RSS, not Windows working set or private bytes',
                            'No frozen EXE or real Windows tray was built or measured',
                            'Foreground UI, playback and active worker descendants are outside idle-owner samples'],
            'packaged': False, 'released': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(profile(), ensure_ascii=False, indent=2) + '\n'
    if args.output: args.output.write_text(text, encoding='utf-8')
    else: print(text, end='')
