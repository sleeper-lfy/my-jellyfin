import json
import queue
import subprocess
import sys
import threading
import time

import httpx
import pytest

from lumen.background_service import BackgroundService, command_for_worker


def wait_until(check, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.01)
    assert check()


def worker_command(job, directory, cancel_file, result_file):
    return [sys.executable, '-m', 'lumen.background_worker', job, '--data-dir', str(directory),
            '--cancel-file', str(cancel_file), '--result-file', str(result_file)]


class FakeServer:
    instances = None
    fail_port = None

    def __init__(self, directory, port, remote, budget):
        self.port, self.remote, self.budget = port, remote, budget
        self.lock = threading.RLock()
        self.sessions = {}
        self.clock = time.monotonic
        self.downloads = type('Downloads', (), {'lock': threading.RLock(), 'active': {},
            'pending': queue.Queue(), 'paused': threading.Event()})()
        self.running = False
        self.starts = self.stops = 0
        if self.instances is not None:
            self.instances.append(self)

    def start(self):
        self.starts += 1
        if self.port == self.fail_port:
            raise OSError('private path or token must never cross into status')
        self.running = True

    def stop(self):
        self.stops += 1
        self.running = False


def test_real_lan_survives_gui_handoff_and_respects_saved_configuration(library):
    library.set_setting('lan', {'enabled': True, 'port': 0})
    service = BackgroundService(library.directory, command_factory=worker_command)
    service.start()
    try:
        server = service.server
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}', trust_env=False) as client:
            assert client.get('/api/info').status_code == 401
            assert client.get('/api/info', headers={'Authorization': 'Bearer ' + server.token}).status_code == 200
            service.tick(gui_busy=True)
            assert service.server is server
            assert client.get('/api/info', headers={'Authorization': 'Bearer ' + server.token}).status_code == 200
        service.refresh_configuration()
        assert service.server is server
        library.set_setting('lan', {'enabled': False, 'port': 0})
        service.refresh_configuration()
        assert service.server is None
        library.set_setting('lan', {'enabled': True, 'port': 0})
        service.refresh_configuration()
        assert service.server is not None and service.server.token == server.token
    finally:
        service.stop()
    assert not service.status()['lan']['running']


def test_failed_port_change_restores_old_server_and_cleans_failed_instance(library, monkeypatch):
    instances = []
    monkeypatch.setattr(FakeServer, 'instances', instances)
    monkeypatch.setattr(FakeServer, 'fail_port', 9999)
    library.set_setting('lan', {'enabled': True, 'port': 8097})
    service = BackgroundService(library.directory, server_factory=FakeServer)
    service.start()
    try:
        previous = service.server
        library.set_setting('lan', {'enabled': True, 'port': 9999})
        with pytest.raises(OSError):
            service.refresh_configuration()
        assert service.server is previous and previous.running and previous.starts == 2
        assert instances[-1].stops == 1 and not instances[-1].running
        status = service.status()
        assert status['lan']['port'] == 8097 and status['lan']['error'] == 'OSError'
        assert 'private' not in json.dumps(status)
    finally:
        service.stop()


def test_watch_poll_runs_in_short_lived_process_and_preserves_stability_state(library, tmp_path):
    watched = tmp_path / 'watched'
    watched.mkdir()
    (watched / 'File.2024.mp4').write_bytes(b'fast index before deferred media probe')
    library.set_setting('watched_folders', [{'path': str(watched), 'kind': 'movie', 'settle_seconds': 0}])
    clock = [0.0]
    service = BackgroundService(library.directory, clock=lambda: clock[0], command_factory=worker_command)
    service.start()
    try:
        clock[0] = 10
        service.tick()
        wait_until(lambda: not service.status()['worker']['running'])
        first = service.status()['last_job']
        assert first['job'] == 'watch' and first['status'] == 'ok' and first['summary']['waiting'] == 1
        clock[0] = 20
        service.tick()
        wait_until(lambda: not service.status()['worker']['running'])
        assert service.status()['last_job']['summary']['imported'] == 1
        assert library.db.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 1
        assert library.db.execute('SELECT pending FROM import_cache').fetchone()[0] == 1
        assert service.budget.active == 0
        assert not any(path.is_dir() for path in library.directory.glob('background-*'))
    finally:
        service.stop()


def long_running_command(job, directory, cancel_file, result_file):
    code = ('import os,sys,time,json;from pathlib import Path;'
            'assert os.environ.get("LUMEN_BACKGROUND_WORKER")=="1";'
            'assert "LUMEN_BACKGROUND_SERVICE" not in os.environ;'
            'cancel=Path(sys.argv[1]);result=Path(sys.argv[2]);'
            '\nwhile not cancel.exists(): time.sleep(.01)'
            '\nresult.write_text(json.dumps({"status":"cancelled","summary":{"completed":0}}));sys.exit(2)')
    return [sys.executable, '-c', code, str(cancel_file), str(result_file)]


@pytest.mark.parametrize('reason', ['gui', 'pc', 'lan', 'stop'])
def test_active_worker_yields_to_gui_playback_and_shutdown(library, reason, monkeypatch):
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE', '1')
    library.set_setting('lan', {'enabled': True, 'port': 8097})
    service = BackgroundService(library.directory, server_factory=FakeServer, command_factory=long_running_command)
    service.start()
    try:
        assert service._start_job('watch')
        wait_until(lambda: service.status()['worker']['pid'] is not None)
        if reason == 'gui':
            service.tick(gui_busy=True)
        elif reason == 'pc':
            service.tick(gui_playing=True)
        elif reason == 'lan':
            with service.server.lock:
                service.server.sessions['session'] = {'playing': True, 'time': time.monotonic()}
            service.tick()
        else:
            service.stop()
        wait_until(lambda: not service.status()['worker']['running'])
        assert service.status()['last_job']['status'] == 'cancelled'
        assert service.budget.active == 0 and not service.budget.leases
        assert not any(path.is_dir() for path in library.directory.glob('background-*'))
        if reason in {'lan', 'pc'}:
            assert service.budget.playback
    finally:
        service.stop()


def test_busy_gui_does_not_launch_due_worker_and_watch_resumes_after_gui_exit(library, tmp_path):
    watched = tmp_path / 'empty'
    watched.mkdir()
    library.set_setting('watched_folders', [{'path': str(watched), 'kind': 'movie'}])
    clock = [0.0]
    service = BackgroundService(library.directory, clock=lambda: clock[0], command_factory=worker_command)
    service.start()
    try:
        clock[0] = 100
        service.tick(gui_busy=True)
        assert not service.status()['worker']['running'] and service.status()['last_job'] is None
        service.tick(gui_busy=False)
        wait_until(lambda: service.status()['last_job'] is not None)
        assert service.status()['last_job']['job'] == 'watch'
    finally:
        service.stop()


def test_importing_service_does_not_load_qt_or_mpv(tmp_path):
    result = subprocess.run([sys.executable, '-c',
        'import sys;from lumen.background_service import BackgroundService;'
        'assert not any(name.startswith("PySide6") or name in {"mpv","lumen.mpv_backend"} for name in sys.modules)'],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_worker_command_routes_before_gui_dispatch_and_preserves_paths(tmp_path, monkeypatch):
    command = command_for_worker('watch', tmp_path / 'space folder', tmp_path / 'cancel', tmp_path / 'result')
    assert command[:4] == [sys.executable, '-m', 'lumen', '--background-worker']
    assert command[5:7] == ['--data-dir', str(tmp_path / 'space folder')]
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    frozen = command_for_worker('media', tmp_path, tmp_path / 'cancel', tmp_path / 'result')
    assert frozen[:3] == [sys.executable, '--background-worker', 'media']
    with pytest.raises(ValueError):
        command_for_worker('invalid', tmp_path, tmp_path / 'cancel', tmp_path / 'result')


@pytest.mark.parametrize('needs_ffmpeg,status,delay', [(True, 'done', 60), (False, 'failed', 30)])
def test_pending_media_backs_off_and_retries_after_tool_configuration(library, video_factory, needs_ffmpeg, status, delay):
    source = video_factory('Background pending.2024.mp4')
    library.import_folder(source.parent, 'movie', fast=True)
    clock = [0.0]
    launches = []
    def command(job, directory, cancel_file, result_file):
        launches.append((job, clock[0]))
        payload = {'status': status, 'summary': {'completed': 0, 'needs_ffmpeg': needs_ffmpeg}}
        code = ('import json,sys;from pathlib import Path;'
                'Path(sys.argv[1]).write_text(sys.argv[2]);sys.exit(int(sys.argv[3]))')
        return [sys.executable, '-c', code, str(result_file), json.dumps(payload), '1' if status == 'failed' else '0']
    service = BackgroundService(library.directory, clock=lambda: clock[0], command_factory=command)
    service.start()
    try:
        clock[0] = 2
        service.tick()
        wait_until(lambda: not service.status()['worker']['running'])
        assert launches == [('media', 2)]
        # The still-pending queue must not start a new process on each UI tick.
        assert library.db.execute('SELECT pending FROM import_cache').fetchone()[0] == 1
        library.set_setting('ffmpeg_directory', str(source.parent / 'new tools'))
        for second in range(3, 2 + delay):
            clock[0] = second
            service.tick()
            assert not service.status()['worker']['running']
        assert launches == [('media', 2)]
        # Configuration is re-read by the next short-lived worker. Missing
        # tools never disable the queue, and its retry takes at most 60 seconds.
        clock[0] = 2 + delay
        service.tick()
        wait_until(lambda: not service.status()['worker']['running'])
        assert launches == [('media', 2), ('media', 2 + delay)]
    finally:
        service.stop()
