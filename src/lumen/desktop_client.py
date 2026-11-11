"""Qt-side bridge to the lightweight desktop owner; services stay outside the GUI."""
from __future__ import annotations

from collections import deque
import copy
import queue
import threading
import time
import uuid
import weakref

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .core import ImportCancelled, check_cancelled
from .desktop_runtime import RuntimeClient


class RuntimeTaskBudget:
    """One owner-thread lease per GUI worker in the supervisor's shared budget."""
    def __init__(self, client, limit=1):
        self.client = client
        self.condition = threading.Condition()
        self.limit = max(1, min(3, int(limit)))
        self.paused = bool(client.status.get('budget', {}).get('paused', False))
        self.playback = False
        self._leases = {}
        self._outstanding = set()
        self._closed = False

    @property
    def active(self):
        with self.condition:
            local = len(self._leases)
        return max(local, int(self.client.status.get('budget', {}).get('active', 0)))

    def set_limit(self, limit):
        limit = max(1, min(3, int(limit)))
        self.client.command('budget', limit=limit)
        with self.condition:
            self.limit = limit
            self.condition.notify_all()

    def set_paused(self, paused):
        self.client.command('budget', paused=bool(paused))
        with self.condition:
            self.paused = bool(paused)
            self.condition.notify_all()

    def set_playback(self, playing):
        # Called by the GUI's 500ms timer: publishing uses the separate poll thread.
        with self.condition:
            self.playback = bool(playing)
            self.condition.notify_all()

    def acquire(self, cancelled=None, *, resource=None, background=False):
        if resource not in (None, 'disk', 'cpu', 'network'):
            raise ValueError('未知后台资源类型')
        thread = threading.get_ident()
        with self.condition:
            if thread in self._leases:
                raise RuntimeError('后台任务已经持有执行名额')
        identifier = uuid.uuid4().hex
        held = requested = False
        try:
            while True:
                check_cancelled(cancelled)
                with self.condition:
                    if self._closed:
                        raise ImportCancelled('界面已关闭，任务已停止')
                    if self.paused or background and self.playback:
                        self.condition.wait(.1)
                        continue
                    self._outstanding.add(identifier)
                requested = True
                try:
                    result = self.client.command('lease', op='acquire', identifier=identifier,
                                                 resource=resource, background=bool(background))
                except Exception as error:
                    raise ImportCancelled('后台服务连接中断，任务已安全停止') from error
                check_cancelled(cancelled)
                if result.get('acquired'):
                    with self.condition:
                        self._leases[thread] = (identifier, resource, bool(background))
                    held = True
                    return
                with self.condition:
                    self.condition.wait(.1)
        finally:
            if requested and not held:
                self._release_identifier(identifier)

    def _release_identifier(self, identifier):
        try:
            self.client.command('lease', op='release', identifier=identifier)
        except Exception:
            # Keep it for shutdown cleanup; the owner also releases all leases on child exit.
            return
        with self.condition:
            self._outstanding.discard(identifier)
            self.condition.notify_all()

    def release(self):
        with self.condition:
            lease = self._leases.pop(threading.get_ident(), None)
            self.condition.notify_all()
        if lease:
            self._release_identifier(lease[0])

    def checkpoint(self, cancelled=None):
        check_cancelled(cancelled)
        with self.condition:
            lease = self._leases.get(threading.get_ident())
            closed = self._closed
            yielding = lease and (self.paused or lease[2] and self.playback)
        if closed:
            self.release()
            raise ImportCancelled('界面已关闭，任务已停止')
        if yielding:
            self.release()
            self.acquire(cancelled, resource=lease[1], background=lease[2])

    def close(self):
        with self.condition:
            self._closed = True
            self.condition.notify_all()


class RuntimeDownloads:
    def __init__(self, client):
        self.client = client
        self.lock = threading.RLock()
        self.paused = threading.Event()

    @property
    def active(self):
        return int(self.client.status.get('downloads', {}).get('active', 0))

    def pause(self, paused):
        self.client.command('downloads', op='pause', paused=bool(paused))

    def cancel(self, identifier):
        return bool(self.client.command('downloads', op='cancel', identifier=identifier).get('result'))

    def cancel_all(self):
        return self.client.command('downloads', op='cancel_all').get('result')


class RuntimeLanServer:
    """Compatibility surface for settings, playback budgeting and update-idle checks."""
    clock = staticmethod(time.monotonic)

    def __init__(self, client):
        self.client = client
        self.lock = threading.RLock()
        self.downloads = RuntimeDownloads(client)

    def __bool__(self):
        return bool(self.client.status.get('lan', {}).get('running'))

    @property
    def port(self):
        return int(self.client.status.get('lan', {}).get('port', 8097))

    @property
    def sessions(self):
        records = self.client.status.get('sessions', [])
        return records if isinstance(records, dict) else {str(i): item for i, item in enumerate(records)}

    def stop(self):
        # A child window closing never owns the supervisor's listening socket.
        return None


class GuiRuntimeClient(QObject):
    """Network polling lives on a Python thread; Qt objects are touched only by slots."""
    received = Signal(object)
    failed = Signal(str)

    def __init__(self, directory):
        super().__init__()
        self.directory = directory
        self._poll = RuntimeClient(directory, timeout=1.5)
        self._commands = RuntimeClient(directory, timeout=3)
        self.owner_pid = getattr(self._poll, 'pid', None)
        self._rpc_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._status = {}
        self._status_at = 0.0
        self._available = False
        self._window = None
        self.exit_requested = False
        self._quit_handled = False
        self._exit_request_id = None
        self._show_ack_id = None
        self._delivery_pending=threading.Event()
        self._tray_close_scheduled = False
        self._snapshot = {'remote': {'available': False}, 'busy': True,
                          'playing': False, 'closing': False, 'accept_commands': False}
        self._stopped = threading.Event()
        self._thread = None
        self._pending_commands = deque()
        self._events = deque()
        self._seen = set()
        self._seen_order = deque()
        self.received.connect(self._deliver)
        self.failed.connect(self._show_error)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._capture)
        initial = self._poll.request('poll', snapshot=copy.deepcopy(self._snapshot))
        self._accept_status(initial)
        self._buffer(initial)
        self.lan_server = RuntimeLanServer(self)
        self.task_budget = RuntimeTaskBudget(self, self.status.get('budget', {}).get('limit', 1))
        self._sync_downloads()

    @property
    def status(self):
        with self._state_lock:
            return copy.deepcopy(self._status)

    @property
    def fresh(self):
        with self._state_lock:
            return self._available and time.monotonic() - self._status_at < 3

    def _accept_status(self, result):
        status = result.get('status', result)
        if not isinstance(status, dict) or 'lan' not in status:
            return
        with self._state_lock:
            self._status = copy.deepcopy(status)
            self._status_at = time.monotonic()
            self._available = True
        if hasattr(self, 'lan_server'):
            self._sync_downloads()

    def _sync_downloads(self):
        paused = bool(self.status.get('downloads', {}).get('paused'))
        self.lan_server.downloads.paused.set() if paused else self.lan_server.downloads.paused.clear()

    def command(self, action, **fields):
        with self._rpc_lock:
            result = self._commands.request(action, **fields)
            self._accept_status(result)
        return result

    def apply_lan(self, enabled, port):
        self.command('lan', enabled=bool(enabled), port=int(port))
        state = self.status.get('lan', {})
        if enabled and not state.get('running'):
            raise OSError(state.get('error') or '局域网服务未启动')
        return self.lan_server

    def request_exit(self):
        result=self.command('exit')
        self.exit_requested=True
        return result

    def attach(self, window):
        self._window = weakref.ref(window)
        window.shutdownFinished.connect(self.stop)
        self._capture()
        self._deliver({})
        if self._stopped.is_set():
            return
        self.timer.start()
        self._thread = threading.Thread(target=self._run, name='GuiRuntimePoll', daemon=True)
        self._thread.start()

    def _capture(self):
        window = self._window() if self._window else None
        if window is None or self._stopped.is_set():
            return
        remote = window.remote.state()
        snapshot = {'remote': remote,
                    'busy': bool(window.jobs or window.job_queue or window._browse_job or window._auxiliary_jobs),
                    'playing': bool(remote.get('playing')), 'closing': bool(window._closing),
                    'accept_commands': not window._closing and len(self._pending_commands)<32 and not window.remote.pending.full()}
        if self._quit_handled and not window._closing:
            snapshot['exit_cancelled']=True
            snapshot['exit_request_id']=self._exit_request_id
        if getattr(window,'_tray_requested',False) and not self._tray_close_scheduled and not window._closing and not self.gui_active(window):
            self._tray_close_scheduled=True
            def release():
                self._tray_close_scheduled=False
                if getattr(window,'_tray_requested',False) and not window._closing and not self.gui_active(window):window.close()
            QTimer.singleShot(0,release)
        if self._show_ack_id is not None:snapshot['show_ack_id']=self._show_ack_id
        with self._state_lock:
            self._snapshot = snapshot
        self._flush(window)

    @staticmethod
    def gui_active(window):
        from PySide6.QtMultimedia import QMediaPlayer
        player=window.player
        playing=player.media.playbackState()!=QMediaPlayer.PlaybackState.StoppedState
        playback=player.session is not None or (player.isVisible() and player.file is not None) or playing
        return bool(playback or window.jobs or window.job_queue or window._browse_job or window._auxiliary_jobs)

    def _run(self):
        previous_error = None
        try:
            while not self._stopped.is_set():
                if self._delivery_pending.is_set():
                    self._stopped.wait(.1)
                    continue
                try:
                    with self._state_lock:
                        snapshot = copy.deepcopy(self._snapshot)
                    with self._rpc_lock:
                        result = self._poll.request('poll', snapshot=snapshot)
                        self._accept_status(result)
                    self._delivery_pending.set()
                    self.received.emit(result)
                    previous_error = None
                except Exception as error:
                    with self._state_lock:
                        self._available = False
                    message = str(error)
                    if message != previous_error:
                        self.failed.emit(message)
                        previous_error = message
                self._stopped.wait(.5)
        finally:
            try:
                with self._rpc_lock:
                    final={'remote': {'available': False}, 'busy': False,'playing': False, 'closing': True,'accept_commands': False}
                    if self._show_ack_id is not None:final['show_ack_id']=self._show_ack_id
                    self._poll.request('poll', snapshot=final)
            except Exception:
                pass

    def _buffer(self, result):
        for item in result.get('commands', []):
            if not isinstance(item, dict) or item.get('id') in self._seen:
                continue
            identifier = item.get('id')
            if not isinstance(identifier, str) or not isinstance(item.get('created'), (int, float)) or not isinstance(item.get('command'), dict):
                continue
            self._seen.add(identifier)
            self._seen_order.append(identifier)
            if len(self._seen_order) > 256:
                self._seen.discard(self._seen_order.popleft())
            self._pending_commands.append(item)
        self._events.extend(event for event in result.get('events', []) if event in ('show', 'quit'))

    @Slot(object)
    def _deliver(self, result):
        try:self._deliver_result(result)
        finally:self._delivery_pending.clear()

    def _deliver_result(self, result):
        if self._stopped.is_set():
            return
        status=result.get('status',self.status)
        if status.get('exit_requested') is False and self._quit_handled:
            self.exit_requested=False
            self._quit_handled=False
            self._exit_request_id=None
        self._buffer(result)
        window = self._window() if self._window else None
        if window is None:
            return
        self._flush(window)
        while self._events:
            event = self._events.popleft()
            if event == 'show' and not window._closing:
                window._tray_requested=False
                window.showNormal()
                window.raise_()
                window.activateWindow()
                self._show_ack_id=status.get('show_request_id')
                self._capture()
            elif event == 'quit':
                self.exit_requested=True
                self._quit_handled=True
                self._exit_request_id=status.get('exit_request_id')
                window.close()
        if not self._stopped.is_set():self._capture()

    def _flush(self, window):
        if window._closing:
            return
        while self._pending_commands:
            item = self._pending_commands[0]
            try:
                window.remote.pending.put_nowait((item['id'], item['created'], item['command']))
            except queue.Full:
                break
            self._pending_commands.popleft()

    @Slot(str)
    def _show_error(self, message):
        window = self._window() if self._window else None
        if window is not None and not window._closing and not self._stopped.is_set():
            window.status.setText('后台连接暂不可用：' + message)

    def idle(self):
        if not self.fresh:
            return False
        state = self.status
        if state.get('budget', {}).get('active') or state.get('downloads', {}).get('active'):
            return False
        return not any(time.monotonic() - record.get('time', 0) < 30
                       for record in self.lan_server.sessions.values())

    def stop(self):
        if self._stopped.is_set():
            return
        self.timer.stop()
        self.task_budget.close()
        self._stopped.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.8)
