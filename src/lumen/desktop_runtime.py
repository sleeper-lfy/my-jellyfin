"""Small desktop owner: native tray + LAN; Qt lives only in a disposable child."""
from __future__ import annotations

import hmac
import json
import logging
import os
from pathlib import Path
import queue
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler

RUNTIME_FILE = 'desktop-runtime.json'
MAX_MESSAGE = 131072


def command(arguments):
    if getattr(sys, 'frozen', False):
        return [sys.executable, *arguments]
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.with_name('pythonw.exe').is_file():
        executable = executable.with_name('pythonw.exe')
    return [str(executable), '-m', 'lumen', *arguments]


class RuntimeLock:
    """OS-owned lock, automatically released on crashes; no Qt DLL needed."""
    def __init__(self, directory):
        self.path = Path(directory) / 'desktop-runtime.lock'
        self.stream = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            stream.write(b'\0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            return False
        self.stream = stream
        return True

    def close(self):
        if self.stream:
            self.stream.close(); self.stream = None


class RuntimeClient:
    """Current-user loopback IPC; never uses LAN credentials or HTTP proxies."""
    def __init__(self, directory, *, timeout=12):
        path = Path(directory) / RUNTIME_FILE
        if path.stat().st_size > 4096:
            raise OSError('后台连接信息无效')
        data = json.loads(path.read_text(encoding='utf-8'))
        self.port, self.token = data['port'], data['token']
        self.pid = data.get('pid')
        if type(self.port) is not int or not 1 <= self.port <= 65535 or not isinstance(self.token, str) or len(self.token) != 64:
            raise OSError('后台连接信息无效')
        self.opener = build_opener(ProxyHandler({}))
        self.timeout = timeout

    def request(self, action, **fields):
        body = json.dumps({'action': action, **fields}, ensure_ascii=False, allow_nan=False).encode()
        if len(body) > MAX_MESSAGE:
            raise ValueError('后台请求过大')
        request = Request(f'http://127.0.0.1:{self.port}/control', body,
                          {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=self.timeout) as response:
            data = response.read(MAX_MESSAGE + 1)
        if len(data) > MAX_MESSAGE:
            raise OSError('后台响应过大')
        result = json.loads(data)
        if not result.get('ok', False):
            raise OSError(result.get('error', '后台操作未完成'))
        return result.get('result', {})


class RemoteMailbox:
    def __init__(self, wake):
        self.wake = wake
        self.pending = queue.Queue(32)
        self.lock = threading.Lock()
        self.idle_snapshot = {'available': True, 'active': False, 'title': '', 'position': 0, 'duration': 0, 'playing': False}
        self.snapshot = dict(self.idle_snapshot)

    def state(self):
        with self.lock:
            return json.loads(json.dumps(self.snapshot))

    def submit(self, body):
        from .remote_commands import validate_command
        import uuid
        value = validate_command(body)
        identifier = uuid.uuid4().hex
        try:
            self.pending.put_nowait({'id': identifier, 'created': time.monotonic(), 'command': value})
        except queue.Full:
            raise ValueError('遥控命令过多，请稍后重试') from None
        self.wake()
        return identifier

    def take(self):
        values = []
        for _ in range(32):
            try:
                item = self.pending.get_nowait()
            except queue.Empty:
                break
            if time.monotonic() - item['created'] <= 10:
                values.append(item)
        return values

    def clear(self, *, preserve_pending=False):
        if not preserve_pending:
            self.take()
        with self.lock:
            self.snapshot = dict(self.idle_snapshot)


class LeaseManager:
    """Keep GUI worker leases on owner threads in the shared service budget."""
    def __init__(self, budget):
        self.budget = budget
        self.items = {}
        self.lock = threading.Lock()

    def acquire(self, identifier, resource, background):
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 80 or resource not in (None, 'disk', 'cpu', 'network'):
            raise ValueError('无效任务名额')
        with self.lock:
            item = self.items.get(identifier)
            if item is None:
                if len(self.items) >= 32:
                    raise ValueError('任务名额过多')
                item = {'cancel': threading.Event(), 'ready': threading.Event()}
                self.items[identifier] = item
                def run():
                    acquired = False
                    try:
                        self.budget.acquire(item['cancel'].is_set, resource=resource, background=bool(background))
                        acquired = True; item['ready'].set()
                        item['cancel'].wait()
                    except Exception:
                        pass
                    finally:
                        if acquired:
                            self.budget.release()
                threading.Thread(target=run, name='DesktopTaskLease', daemon=True).start()
            return {'acquired': item['ready'].is_set() and not item['cancel'].is_set()}

    def release(self, identifier):
        with self.lock:
            item = self.items.pop(identifier, None)
        if item:
            item['cancel'].set()
        return {'released': bool(item)}

    def clear(self):
        with self.lock:
            items, self.items = self.items, {}
        for item in items.values():
            item['cancel'].set()


class DesktopRuntime:
    def __init__(self, directory, *, tray=True, open_window=True, service=None):
        self.directory = Path(directory).resolve()
        self.use_tray, self.open_window = tray, open_window
        self.lock = RuntimeLock(self.directory)
        self.events = queue.Queue(64)
        self.gui_events = queue.Queue(32)
        self.remote = RemoteMailbox(self.open)
        self.service = service
        self.leases = LeaseManager(service.budget) if service else None
        self.child = None
        self.gui_snapshot = {}
        self.exit_requested = False
        self.exit_sent = 0
        self.exit_request_id = None
        self.show_request_id = None
        self.stopping = threading.Event()
        self.token = secrets.token_hex(32)
        self.http = None
        self.tray = None
        self.last_refresh = 0

    def open(self):
        try: self.events.put_nowait(('open', None, None))
        except queue.Full: pass

    def exit(self):
        try: self.events.put_nowait(('exit', None, None))
        except queue.Full: pass

    def _status(self):
        result = self.service.status()
        server = self.service.server
        if server and server.lock.acquire(blocking=False):
            try:
                result['sessions'] = [{'time': state['time'], 'playing': bool(state.get('playing'))}
                                      for state in list(server.sessions.values())[-128:]]
            finally: server.lock.release()
        elif server:
            result['sessions'] = [{'time': time.monotonic(), 'playing': True}]
        else: result['sessions'] = []
        result['budget'] = {key: getattr(self.service.budget, key) for key in ('active', 'paused', 'playback', 'limit')}
        result['gui_running'] = self.child is not None and self.child.poll() is None
        result['exit_requested'] = self.exit_requested
        result['exit_request_id'] = self.exit_request_id
        result['show_request_id'] = self.show_request_id
        return result

    def _launch(self):
        if self.child is not None and self.child.poll() is None:
            self.show_request_id = secrets.token_hex(8)
            try: self.gui_events.put_nowait('show')
            except queue.Full: pass
            return
        environment = dict(os.environ)
        environment.pop('LUMEN_BACKGROUND_SERVICE', None)
        self.child = subprocess.Popen(command(['--desktop-child', '--data-dir', str(self.directory)]),
                                      env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, close_fds=True,
                                      creationflags=0x08000000 if os.name == 'nt' else 0)
        self.show_request_id = None

    def _dispatch(self, action, fields):
        if action in ('ping', 'status'):
            return self._status()
        if action == 'open':
            self._launch(); return self._status()
        if action == 'exit':
            self.exit_requested = True
            self.exit_request_id = secrets.token_hex(8)
            if self.child is not None and self.child.poll() is None:
                self.gui_events.put('quit'); self.exit_sent = time.monotonic()
            return {'exiting': True}
        if action == 'poll':
            value = fields.get('snapshot', {})
            if not isinstance(value, dict) or not isinstance(value.get('remote', {}), dict):
                raise ValueError('无效界面状态')
            self.gui_snapshot = value
            if self.exit_requested and value.get('exit_cancelled') is True and value.get('exit_request_id') == self.exit_request_id:
                self.exit_requested = False; self.exit_sent = 0; self.exit_request_id = None
            if self.show_request_id and value.get('show_ack_id') == self.show_request_id:
                self.show_request_id = None
            with self.remote.lock:
                self.remote.snapshot = value.get('remote', {})
            events = []
            while not self.gui_events.empty():
                try: events.append(self.gui_events.get_nowait())
                except queue.Empty: break
            return {'commands': self.remote.take() if value.get('accept_commands', True) else [],
                    'events': events, 'status': self._status()}
        if action == 'lan':
            enabled, port = fields.get('enabled'), fields.get('port')
            if type(enabled) is not bool or type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError('无效局域网配置')
            from .core import Library
            library = Library(self.directory)
            try:
                old = library.setting('lan', {})
                library.set_setting('lan', {'enabled': enabled, 'port': port})
                try:
                    self.service.refresh_configuration()
                    status = self.service.status()
                    if enabled and not status['lan'].get('running'):
                        raise OSError(status['lan'].get('error') or '局域网服务未启动')
                except Exception:
                    library.set_setting('lan', old)
                    self.service.refresh_configuration()
                    raise
            finally:
                library.close()
            return self._status()
        if action == 'budget':
            if 'limit' in fields:
                limit = fields['limit']
                if type(limit) is not int or not 1 <= limit <= 3: raise ValueError('无效并发上限')
                self.service.budget.set_limit(limit)
            if 'paused' in fields:
                if type(fields['paused']) is not bool: raise ValueError('无效暂停状态')
                self.service.budget.set_paused(fields['paused'])
            return self._status()
        if action == 'lease':
            if fields.get('op') == 'acquire':
                return self.leases.acquire(fields.get('identifier'), fields.get('resource'), fields.get('background', False))
            if fields.get('op') == 'release':
                return self.leases.release(fields.get('identifier'))
            raise ValueError('无效任务名额操作')
        if action == 'downloads':
            downloads = self.service.server.downloads if self.service.server else None
            if not downloads: return {'result': False}
            operation = fields.get('op')
            if operation == 'pause':
                downloads.pause(bool(fields.get('paused'))); result = True
            elif operation == 'cancel': result = downloads.cancel(str(fields.get('identifier', '')))
            elif operation == 'cancel_all': downloads.cancel_all(); result = True
            else: raise ValueError('无效下载操作')
            return {'result': result}
        raise ValueError('无效后台操作')

    def _serve_control(self):
        runtime = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'
            def log_message(self, *_): pass
            def do_POST(self):
                self.connection.settimeout(3)
                if self.path != '/control' or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + runtime.token):
                    self.send_error(403); return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= MAX_MESSAGE: raise ValueError('无效后台请求大小')
                    message = json.loads(self.rfile.read(size))
                    if not isinstance(message, dict): raise ValueError('无效后台请求')
                    action = message.pop('action', '')
                    event, result = threading.Event(), {}
                    runtime.events.put_nowait((action, message, (event, result)))
                    if not event.wait(10): raise OSError('后台正在处理任务，请稍后重试')
                    value = result
                except Exception:
                    value = {'ok': False, 'error': '后台请求未完成，请稍后重试'}
                data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers()
                try: self.wfile.write(data)
                except OSError: pass
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.http.daemon_threads = True
        threading.Thread(target=self.http.serve_forever, name='DesktopControl', daemon=True).start()
        path = self.directory / RUNTIME_FILE
        temporary = path.with_suffix('.tmp')
        descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump({'port': self.http.server_port, 'token': self.token, 'pid': os.getpid()}, stream)
        temporary.replace(path)

    def _start_tray(self):
        from .windows_tray import WindowsTray
        icon_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        self.tray = WindowsTray(self.open, self.exit, icon_path=icon_root / 'assets' / 'lumen.ico')
        def run():
            try: self.tray.run()
            except Exception:
                logging.exception('Desktop tray failed; stopping background owner')
                self.exit()
        threading.Thread(target=run, name='WindowsTray', daemon=True).start()

    def run(self):
        if not self.lock.acquire():
            for _ in range(30):
                try:
                    RuntimeClient(self.directory).request('open' if self.open_window else 'ping')
                    return 0
                except (OSError, ValueError, KeyError):
                    time.sleep(.1)
            raise OSError('Lumen 后台已运行，但暂时无法连接；请稍后重试')
        try:
            os.environ['LUMEN_BACKGROUND_SERVICE'] = '1'
            from .image_isolation import register_shutdown_event
            register_shutdown_event(self.stopping)
            if self.service is None:
                from .background_service import BackgroundService
                self.service = BackgroundService(self.directory, remote=self.remote)
                self.leases = LeaseManager(self.service.budget)
            try: self.service.start()
            except Exception: logging.exception('LAN did not start; desktop remains available')
            self._serve_control()
            if self.use_tray: self._start_tray()
            show_window=self.open_window
            if show_window and self.use_tray:
                from .startup import silent_start_enabled
                try:show_window=not silent_start_enabled(self.directory)
                except (OSError,ValueError,sqlite3.Error):
                    logging.exception('Cannot read silent startup preference; opening the main window')
            if show_window: self._launch()
            while not self.stopping.is_set():
                try:
                    action, fields, response = self.events.get(timeout=.2)
                    try: result = {'ok': True, 'result': self._dispatch(action, fields or {})}
                    except Exception as error:
                        logging.exception('Desktop operation failed')
                        result = {'ok': False, 'error': str(error)}
                    if response:
                        event, target = response; target.update(result); event.set()
                except queue.Empty:
                    pass
                if self.child is not None and self.child.poll() is not None:
                    self.child = None; self.gui_snapshot = {}
                    self.remote.clear(preserve_pending=bool(self.show_request_id and not self.exit_requested))
                    self.leases.clear()
                    if self.show_request_id and not self.exit_requested:
                        self._launch()
                if self.exit_requested:
                    if self.child is None: break
                else:
                    self.service.tick(gui_busy=self.child is not None, gui_playing=bool(self.gui_snapshot.get('playing')))
                if time.monotonic() - self.last_refresh >= 2:
                    self.last_refresh = time.monotonic()
                    try:
                        self.service.refresh_configuration()
                        from .core import Library
                        from .power import shutdown_supported
                        library = Library(self.directory, initialize=False, timeout=.15)
                        try:
                            self.remote.idle_snapshot.update(shutdown_supported=shutdown_supported(),
                                shutdown_allowed=bool(library.setting('remote_shutdown_enabled', False)))
                            if self.child is None:
                                with self.remote.lock:
                                    self.remote.snapshot = dict(self.remote.idle_snapshot)
                        finally: library.close()
                    except Exception: logging.exception('Background settings refresh failed')
        finally:
            self.stopping.set()
            if self.leases: self.leases.clear()
            if self.tray: self.tray.stop()
            if self.service: self.service.stop()
            if self.http:
                self.http.shutdown(); self.http.server_close()
            path = self.directory / RUNTIME_FILE
            try:
                if json.loads(path.read_text(encoding='utf-8')).get('token') == self.token:
                    path.unlink(missing_ok=True)
            except (OSError, ValueError): pass
            self.lock.close()
        return 0


def run_desktop(directory, *, background=False, tray=True):
    runtime = DesktopRuntime(directory, tray=tray and sys.platform == 'win32', open_window=not background)
    if threading.current_thread() is threading.main_thread():
        for kind in (signal.SIGINT, signal.SIGTERM):
            signal.signal(kind, lambda *_: runtime.exit())
    return runtime.run()
