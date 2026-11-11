"""Qt-free resident LAN owner and cancellable, short-lived background jobs."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

from .core import ImportCancelled, Library
from .task_journal import TaskBudget

log = logging.getLogger(__name__)
JOBS = ('media', 'watch', 'discovery', 'inspect')
INTERVALS = {'media': 1.5, 'watch': 10, 'discovery': 60, 'inspect': 1800}
INITIAL_DELAYS = {'media': 1.5, 'watch': 10, 'discovery': 4, 'inspect': 600}


def command_for_worker(job, directory, cancel_file, result_file):
    if job not in JOBS:
        raise ValueError('未知后台任务')
    command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'lumen']
    return [*command, '--background-worker', job, '--data-dir', str(directory),
            '--cancel-file', str(cancel_file), '--result-file', str(result_file)]


class _ProcessTree:
    """Own descendants without imposing an artificial task memory limit."""
    def __init__(self, process):
        self.process = process
        self.handle = None
        self._close_lock = threading.Lock()
        self._closed = False
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('user', ctypes.c_int64), ('job_user', ctypes.c_int64), ('flags', wintypes.DWORD),
                        ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('read', 'write', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        limits = Limits()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no working-set/memory cap.
        try:
            if not self.handle or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None
            elif os.name != 'nt':
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


@dataclass
class _Job:
    name: str
    temporary: object
    cancel_file: Path
    result_file: Path
    cancelled: threading.Event = field(default_factory=threading.Event)
    process: object = None
    tree: object = None
    thread: object = None


def _summary(value, depth=0):
    """Only bounded numeric task results cross into a GUI status response."""
    if not isinstance(value, dict) or depth > 2:
        return {}
    result = {}
    for key, item in list(value.items())[:24]:
        if not isinstance(key, str) or len(key) > 40:
            continue
        if type(item) in (int, bool) or item is None or type(item) is float and math.isfinite(item):
            result[key] = item
        elif isinstance(item, dict):
            result[key] = _summary(item, depth + 1)
    return result


class BackgroundService:
    """Call tick from a native loop; no Qt imports or persistent GUI objects."""
    def __init__(self, directory, remote=None, *, clock=time.monotonic, wall_clock=time.time,
                 server_factory=None, command_factory=command_for_worker):
        self.directory = Path(directory).resolve()
        self.remote = remote
        self.clock, self.wall_clock = clock, wall_clock
        self._server_factory, self._command_factory = server_factory, command_factory
        library = Library(self.directory)
        try:
            self.budget = TaskBudget(library.setting('background_concurrency', 1))
        finally:
            library.close()
        self.server = None
        self._configuration = {'enabled': False, 'port': 8097}
        self._server_port = None
        self._error = ''
        self._lock = threading.RLock()
        self._job = None
        self._last_job = None
        self._started = False
        self._closing = threading.Event()
        self._gui_busy = self._gui_playing = False
        self._lan_state = {'sessions': 0, 'playing': False, 'downloads': {'active': 0, 'pending': 0, 'paused': False}}
        now = self.clock()
        self._due = {job: now + delay for job, delay in INITIAL_DELAYS.items()}
        self._configuration_due = now

    def start(self):
        if self._started:
            return
        self._closing.clear()
        self._started = True
        now = self.clock()
        self._due = {job: now + delay for job, delay in INITIAL_DELAYS.items()}
        self.refresh_configuration()

    def refresh_configuration(self):
        library = Library(self.directory, initialize=False, timeout=.15)
        try:
            configuration = library.setting('lan', {})
            if not isinstance(configuration, dict):
                raise ValueError('无效局域网配置')
            enabled = bool(configuration.get('enabled', False))
            port = configuration.get('port', 8097)
            if type(port) is not int or not 0 <= port <= 65535:
                raise ValueError('无效局域网端口')
            self.budget.set_limit(library.setting('background_concurrency', 1))
        finally:
            library.close()
        self._configuration_due = self.clock() + 2
        self._configuration = {'enabled': enabled, 'port': port}
        if not self._started:
            return
        if self.server is not None and enabled and port == self._server_port:
            self._error = ''
            return
        previous = self.server
        previous_port = self._server_port
        if previous is not None:
            previous.stop()
        self.server = None
        self._server_port = None
        if not enabled:
            self._error = ''
            return
        if self._server_factory is None:
            from .server import LanServer
            factory = LanServer
        else:
            factory = self._server_factory
        server = None
        try:
            server = factory(self.directory, port=port, remote=self.remote, budget=self.budget)
            server.start()
            self.server, self._server_port = server, port
            self._error = ''
        except Exception as error:
            self._error = type(error).__name__
            if server is not None:
                try:
                    server.stop()
                except Exception:
                    log.exception('Failed LAN service cleanup failed')
            if previous is not None:
                try:
                    previous.start()
                    self.server, self._server_port = previous, previous_port
                except Exception:
                    log.exception('Previous LAN service could not be restored')
            raise

    def _read_lan_state(self):
        server = self.server
        if server is None:
            return {'sessions': 0, 'playing': False, 'downloads': {'active': 0, 'pending': 0, 'paused': False}}
        result = {**self._lan_state, 'downloads': dict(self._lan_state['downloads'])}
        if server.lock.acquire(blocking=False):
            try:
                result['sessions'] = min(128, len(server.sessions))
                now = server.clock()
                result['playing'] = any(state.get('playing') and now - state['time'] < 5 for state in server.sessions.values())
            finally:
                server.lock.release()
        else:
            # Busy persistence must not stall the native tray message loop.
            result['playing'] = True
        downloads = server.downloads
        if downloads is not None and downloads.lock.acquire(blocking=False):
            try:
                result['downloads'] = {'active': min(16, len(downloads.active)),
                                       'pending': min(16, downloads.pending.qsize()),
                                       'paused': downloads.paused.is_set()}
            finally:
                downloads.lock.release()
        return result

    def _eligible(self, library, job):
        if job == 'media':
            return bool(library.db.execute('SELECT 1 FROM import_cache WHERE pending IN (1,2) LIMIT 1').fetchone())
        if job == 'watch':
            return (any(isinstance(row, dict) and row.get('enabled', True) for row in library.setting('watched_folders', []))
                    or bool(library.db.execute("SELECT 1 FROM tasks WHERE kind='ingest' AND status IN ('queued','running','retry') LIMIT 1").fetchone()))
        if job == 'inspect':
            last = library.setting('inspection', {}).get('last', 0)
            return (self.wall_clock() - last >= 7200
                    and bool(library.db.execute('SELECT 1 FROM files LIMIT 1').fetchone()))
        from .plugins import Plugins
        return any(plugin['config'].get('enabled') and 'discover' in plugin['capabilities']
                   and plugin['config'].get('auto_refresh', False)
                   and self.wall_clock() - max(plugin['config'].get('last_refresh', 0), plugin['config'].get('last_attempt', 0))
                   > max(1, plugin['config'].get('interval_hours', 24)) * 3600
                   for plugin in Plugins(library).installed())

    def tick(self, gui_busy=False, gui_playing=False):
        if not self._started or self._closing.is_set():
            return
        self._gui_busy, self._gui_playing = bool(gui_busy), bool(gui_playing)
        now = self.clock()
        if now >= self._configuration_due:
            try:
                self.refresh_configuration()
            except Exception as error:
                self._error = type(error).__name__
                self._configuration_due = now + 10
                log.exception('Background configuration refresh failed')
        self._lan_state = self._read_lan_state()
        playing = self._gui_playing or self._lan_state['playing']
        self.budget.set_playback(playing)
        if self._gui_busy or playing or self.budget.paused:
            self.cancel_worker()
            return
        with self._lock:
            if self._job is not None:
                return
        if not any(now >= deadline for deadline in self._due.values()):
            return
        library = None
        try:
            library = Library(self.directory, initialize=False, timeout=.15)
            for job in JOBS:
                if now < self._due[job]:
                    continue
                self._due[job] = now + INTERVALS[job]
                if self._eligible(library, job):
                    self._start_job(job)
                    break
        except Exception as error:
            self._error = type(error).__name__
            log.exception('Background eligibility check failed')
        finally:
            if library is not None:
                library.close()

    def _start_job(self, name):
        with self._lock:
            if self._job is not None or self._closing.is_set():
                return False
            temporary = tempfile.TemporaryDirectory(prefix='background-', dir=self.directory)
            folder = Path(temporary.name)
            job = _Job(name, temporary, folder / 'cancel', folder / 'result.json')
            self._job = job
            job.thread = threading.Thread(target=self._run_job, args=(job,), name='LumenBackgroundJob', daemon=True)
            job.thread.start()
            return True

    def _run_job(self, job):
        acquired = False
        status, summary, error_type = 'cancelled', {}, ''
        try:
            cancelled = lambda: self._closing.is_set() or job.cancelled.is_set()
            resource = {'media': 'cpu', 'discovery': 'network'}.get(job.name, 'disk')
            self.budget.acquire(cancelled, resource=resource, background=True)
            acquired = True
            if cancelled():
                return
            environment = dict(os.environ)
            # This child is already disposable; image code may load Qt here
            # instead of starting another helper inherited from the LAN owner.
            environment.pop('LUMEN_BACKGROUND_SERVICE', None)
            environment['LUMEN_BACKGROUND_WORKER'] = '1'
            environment['PYTHONUNBUFFERED'] = '1'
            command = self._command_factory(job.name, self.directory, job.cancel_file, job.result_file)
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, env=environment,
                                       creationflags=0x08000000 if os.name == 'nt' else 0,
                                       start_new_session=os.name != 'nt')
            with self._lock:
                job.process = process
                job.tree = _ProcessTree(process)
            while process.poll() is None:
                if cancelled():
                    self._cancel_job(job)
                try:
                    process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    pass
            status = 'ok' if process.returncode == 0 else 'cancelled' if process.returncode == 2 or cancelled() else 'error'
            if job.result_file.is_file() and job.result_file.stat().st_size <= 16384:
                result = json.loads(job.result_file.read_text(encoding='utf-8'))
                if isinstance(result, dict):
                    summary = _summary(result.get('summary', result))
                    if result.get('status') in {'done', 'partial', 'cancelled', 'failed'}:
                        status = {'done': 'ok', 'partial': 'partial', 'cancelled': 'cancelled', 'failed': 'error'}[result['status']]
                    kind = result.get('error_type', '')
                    if isinstance(kind, str) and kind.isidentifier() and len(kind) <= 80:
                        error_type = kind
        except ImportCancelled:
            status = 'cancelled'
        except Exception as error:
            status, error_type = 'error', type(error).__name__
            log.exception('Isolated background job failed')
        finally:
            if job.tree is not None:
                job.tree.close()
            if job.process is not None:
                if job.process.poll() is None:
                    job.process.kill()
                job.process.wait()
            if acquired:
                self.budget.release()
            job.temporary.cleanup()
            with self._lock:
                if job.name == 'media':
                    # Missing tools leave the durable queue pending. Polling it
                    # every 1.5 seconds would otherwise keep spawning processes.
                    # A new FFmpeg configuration is picked up within one minute.
                    delay = 60 if summary.get('needs_ffmpeg') else 30 if status in {'error', 'partial'} else INTERVALS['media']
                    self._due['media'] = max(self._due['media'], self.clock() + delay)
                self._last_job = {'job': job.name, 'status': status, 'summary': summary, 'error_type': error_type}
                if self._job is job:
                    self._job = None

    def _cancel_job(self, job):
        job.cancelled.set()
        try:
            job.cancel_file.touch(exist_ok=True)
        except FileNotFoundError:
            pass  # A just-finished worker already cleaned its private folder.

    def cancel_worker(self):
        with self._lock:
            job = self._job
            if job is not None:
                self._cancel_job(job)

    def status(self):
        with self._lock:
            job = self._job
            worker = {'running': job is not None, 'job': job.name if job else None,
                      'pid': job.process.pid if job and job.process else None,
                      'cancel_requested': job.cancelled.is_set() if job else False}
            last_job = self._last_job
        state = self._read_lan_state()
        return {'lan': {**self._configuration, 'running': self.server is not None,
                        'port': self.server.port if self.server else self._configuration['port'], 'error': self._error},
                'sessions': state['sessions'], 'playing': self._gui_playing or state['playing'],
                'downloads': state['downloads'], 'worker': worker, 'last_job': last_job,
                'paused': self.budget.paused, 'gui_busy': self._gui_busy}

    def stop(self):
        self._closing.set()
        self.cancel_worker()
        with self._lock:
            job = self._job
        if job is not None:
            job.thread.join(timeout=5)
            if job.thread.is_alive():
                with self._lock:
                    if job.tree is not None:
                        job.tree.close()
                    elif job.process is not None:
                        job.process.kill()
                job.thread.join(timeout=3)
        if self.server is not None:
            self.server.stop()
            self.server = None
            self._server_port = None
        self._started = False
