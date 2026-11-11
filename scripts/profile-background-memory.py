"""Measure Linux background RSS/PSS using a disposable library and real workers.

Run with the project's Python environment. This is evidence, not a Windows
working-set assertion or a 50 MB pass/fail gate. No user library is opened.
"""
import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def memory(pid):
    status = Path(f'/proc/{pid}/status').read_text()
    values = {}
    for line in status.splitlines():
        name, _, value = line.partition(':')
        if name in ('VmRSS', 'VmHWM', 'RssAnon', 'RssFile'):
            values[name + '_bytes'] = int(value.split()[0]) * 1024
    for line in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines():
        name, _, value = line.partition(':')
        if name in ('Pss', 'Private_Clean', 'Private_Dirty'):
            values[name + '_bytes'] = int(value.split()[0]) * 1024
    return values


def profile():
    if not sys.platform.startswith('linux'):
        raise SystemExit('This probe requires Linux /proc. It does not measure Windows memory.')
    import os
    import threading
    samples = []
    def sample(stage):
        gc.collect()
        values = memory(os.getpid())
        maps = Path('/proc/self/maps').read_text()
        values.update(stage=stage, rss_mib=round(values['VmRSS_bytes'] / 1048576, 3),
                      pss_mib=round(values['Pss_bytes'] / 1048576, 3),
                      qt_modules=sorted(name for name in sys.modules if name.startswith('PySide6.')),
                      qt_mapped='libQt6' in maps, mpv_mapped='libmpv' in maps,
                      mpv_module=any(name in sys.modules for name in ('mpv', 'lumen.mpv_backend')),
                      threads=[thread.name for thread in threading.enumerate()])
        samples.append(values)
    sample('python_baseline')
    from lumen.core import Library
    from lumen.background_service import BackgroundService
    from lumen.server import LanServer
    sample('background_modules_imported')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('The real media fixture needs ffmpeg on PATH.')
    clock = [0.0]
    completed_workers = []
    def command(job, directory, cancel_file, result_file):
        return [sys.executable, '-m', 'lumen.background_worker', job,
                '--data-dir', str(directory), '--cancel-file', str(cancel_file), '--result-file', str(result_file)]
    def lan(directory, *, port, remote, budget):
        return LanServer(directory, host='127.0.0.1', port=port, discovery_port=0, remote=remote, budget=budget)
    def finish(service, expected):
        deadline = time.monotonic() + 30
        peak = 0
        while service.status()['worker']['running']:
            pid = service.status()['worker']['pid']
            if pid:
                try:
                    peak = max(peak, memory(pid)['VmRSS_bytes'])
                except (FileNotFoundError, ProcessLookupError):
                    pass
            if time.monotonic() > deadline:
                raise RuntimeError('The disposable background worker did not finish.')
            time.sleep(.02)
        last = service.status()['last_job']
        if not last or last['job'] != expected or last['status'] != 'ok':
            raise RuntimeError('The disposable worker did not complete successfully: ' + str(last))
        completed_workers.append({**last, 'observed_worker_peak_rss_bytes': peak,
                                  'note': 'Sampled child RSS; external FFmpeg/other descendants are not included.'})
    with tempfile.TemporaryDirectory(prefix='lumen-background-memory-') as temporary:
        folder = Path(temporary)
        watched = folder / 'watched'
        watched.mkdir()
        directory = folder / 'library'
        library = Library(directory)
        try:
            library.set_setting('lan', {'enabled': True, 'port': 0})
            library.set_setting('watched_folders', [{'path': str(watched), 'kind': 'movie',
                                                    'enabled': True, 'settle_seconds': 0}])
        finally:
            library.close()
        service = BackgroundService(directory, clock=lambda: clock[0], server_factory=lan, command_factory=command)
        service.start()
        try:
            sample('lan_and_empty_directory_monitor_ready')
            # Empty watch exercises a genuine short-lived worker before new media arrives.
            clock[0] = 10
            service.tick()
            finish(service, 'watch')
            sample('empty_watch_worker_finished')
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'color=c=blue:s=320x180:r=24', '-t', '1', '-c:v', 'mpeg4',
                            '-y', str(watched / 'Sample.2024.mp4')], check=True)
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'color=c=red:s=120x180', '-frames:v', '1', '-y', str(watched / 'poster.jpg')], check=True)
            (watched / 'Sample.2024.nfo').write_text('<movie><title>Disposable sample</title><poster>poster.jpg</poster></movie>')
            for stamp, stage in ((20, 'new_media_observation_worker_finished'), (30, 'nfo_image_ingestion_worker_finished')):
                clock[0] = stamp
                service.tick()
                finish(service, 'watch')
                sample(stage)
            clock[0] = 40
            service.tick()
            finish(service, 'media')
            sample('media_probe_worker_finished')
            library = Library(directory, initialize=False)
            try:
                with library.db:
                    library.db.execute('UPDATE files SET position=.5')
                file_count = library.db.execute('SELECT COUNT(*) FROM files').fetchone()[0]
            finally:
                library.close()
            import urllib.request
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            endpoints = []
            for route in ('/api/info', '/api/works', '/api/continue'):
                request = urllib.request.Request(f'http://127.0.0.1:{service.server.port}' + route,
                                                 headers={'Authorization': 'Bearer ' + service.server.token})
                with opener.open(request) as response:
                    response.read()
                    endpoints.append({'endpoint': route, 'status': response.status})
            time.sleep(.1)
            sample('after_read_only_lan_requests')
            time.sleep(1)
            sample('idle_after_all_workers_exited')
        finally:
            service.stop()
    root = Path(__file__).resolve().parents[1]
    source = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (root / 'src/lumen/background_service.py', root / 'src/lumen/background_worker.py')}
    return {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'platform': sys.platform,
            'python': sys.version.split()[0], 'measurement': 'Linux /proc resident RSS and proportional PSS, bytes; MiB = 1048576 bytes',
            'scope': 'Resident BackgroundService with real LAN/discovery, short-lived watch/NFO image/media workers and disposable data',
            'limitations': ['Not Windows working-set evidence; no packaged executable was built.',
                            'Resident RSS excludes exited workers and active external descendants.',
                            'Idle API probes exclude uncached image requests and media playback.'],
            'source_sha256': source, 'file_count': file_count, 'endpoints': endpoints,
            'workers': completed_workers, 'samples': samples}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    proof = profile()
    payload = json.dumps(proof, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding='utf-8')
    print(payload, end='')
