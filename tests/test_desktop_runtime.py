"""Real Qt-free owner, authenticated IPC and uninterrupted LAN regression."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

import pytest

from lumen.core import Library
from lumen.desktop_runtime import RuntimeClient, RuntimeLock, RemoteMailbox, DesktopRuntime, LeaseManager
from lumen.task_journal import TaskBudget


def wait_until(function, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = function()
        if result: return result
        time.sleep(.03)
    raise AssertionError('Timed out waiting for desktop runtime')


def test_runtime_lock_is_owned_until_process_or_descriptor_closes(tmp_path):
    first, second = RuntimeLock(tmp_path), RuntimeLock(tmp_path)
    assert first.acquire()
    try:
        assert not second.acquire()
    finally: first.close()
    assert second.acquire()
    second.close()


def test_remote_mailbox_preserves_command_identity_and_rejects_bad_inputs():
    wakes = []
    mailbox = RemoteMailbox(lambda: wakes.append(True))
    with pytest.raises(ValueError): mailbox.submit({'action': 'open', 'work_id': -1})
    identifier = mailbox.submit({'action': 'open', 'work_id': 4, 'file_id': 5})
    values = mailbox.take()
    assert values[0]['id'] == identifier and values[0]['command'] == {'action': 'open', 'work_id': 4, 'file_id': 5}
    assert wakes == [True] and mailbox.take() == []
    mailbox.clear()
    assert mailbox.state()['available'] and not mailbox.state()['active']
    identifier = mailbox.submit({'action': 'open', 'work_id': 4})
    mailbox.clear(preserve_pending=True)
    assert mailbox.take()[0]['id'] == identifier


def test_gui_leases_share_the_lan_budget_and_cancel_waiters():
    budget = TaskBudget(1)
    manager = LeaseManager(budget)
    try:
        wait_until(lambda: manager.acquire('gui-first', 'disk', False)['acquired'])
        assert budget.active == 1
        assert not manager.acquire('gui-next', 'cpu', False)['acquired']
        manager.release('gui-next')
        manager.release('gui-first')
        wait_until(lambda: budget.active == 0)
        wait_until(lambda: manager.acquire('new', 'cpu', False)['acquired'])
    finally: manager.clear()
    wait_until(lambda: budget.active == 0)


def test_owner_survives_gui_close_and_queues_quit_only_for_explicit_exit(tmp_path):
    class Server:
        def __init__(self):
            import threading
            self.lock = threading.Lock(); self.sessions = {}
    class Service:
        def __init__(self): self.budget = TaskBudget(); self.server = Server()
        def status(self): return {'lan': {'running': True}, 'downloads': {'active': 0, 'paused': False}}
    class Child:
        def poll(self): return None
    owner = DesktopRuntime(tmp_path, tray=False, open_window=False, service=Service())
    owner.child = Child()
    reply = owner._dispatch('poll', {'snapshot': {'closing': True, 'remote': {'available': True}}})
    assert reply['status']['lan']['running'] and not owner.exit_requested
    owner._dispatch('exit', {})
    assert owner.exit_requested
    assert owner._dispatch('poll', {'snapshot': {}})['events'] == ['quit']


@pytest.mark.parametrize('use_tray,open_window,silent,expected',[
    (True,True,True,False),(True,True,False,True),
    (True,False,False,False),(False,True,True,True),
])
def test_cold_start_honors_silent_option_only_when_tray_can_reopen_window(tmp_path,monkeypatch,use_tray,open_window,silent,expected):
    from lumen import startup,image_isolation
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','0')
    monkeypatch.setattr(image_isolation,'_shutdown_event',None)
    library=Library(tmp_path/'data');library.set_setting(startup.SILENT_START_SETTING,silent);directory=library.directory;library.close()
    actions=[]
    class Service:
        budget=TaskBudget();server=None
        def start(self):actions.append('service')
        def tick(self,**kwargs):owner.stopping.set()
        def stop(self):actions.append('stop')
    owner=DesktopRuntime(directory,tray=use_tray,open_window=open_window,service=Service())
    owner.last_refresh=time.monotonic()
    monkeypatch.setattr(owner,'_serve_control',lambda:actions.append('control'))
    monkeypatch.setattr(owner,'_start_tray',lambda:actions.append('tray'))
    monkeypatch.setattr(owner,'_launch',lambda:actions.append('window'))
    assert owner.run()==0
    assert ('window' in actions)==expected and ('tray' in actions)==use_tray
    assert actions[0]=='service' and actions[-1]=='stop'


@pytest.mark.parametrize('open_window,command',[(True,'open'),(False,'ping')])
def test_relaunch_reopens_existing_silent_owner_without_reading_cold_start_preference(tmp_path,monkeypatch,open_window,command):
    from lumen import desktop_runtime,startup
    commands=[];owner=DesktopRuntime(tmp_path,tray=True,open_window=open_window)
    monkeypatch.setattr(owner.lock,'acquire',lambda:False)
    monkeypatch.setattr(startup,'silent_start_enabled',lambda directory:pytest.fail('already running owner must use explicit open/ping'))
    class Client:
        def __init__(self,*args):pass
        def request(self,value):commands.append(value)
    monkeypatch.setattr(desktop_runtime,'RuntimeClient',Client)
    assert owner.run()==0 and commands==[command]


def test_actual_background_entry_lan_range_single_instance_and_exit(tmp_path):
    directory = tmp_path / 'data'
    library = Library(directory)
    media = tmp_path / 'sample.mp4'; content = bytes(range(256)) * 8192; media.write_bytes(content)
    with library.db:
        identifier = library.db.execute("INSERT INTO works(identity,kind,title,added,metadata) VALUES(?,?,?,?,?)",
                                        ('standby-test', 'movie', 'Synthetic', '2026-11-11', '{}')).lastrowid
        file_id = library.db.execute('INSERT INTO files(work_id,path,root,digest,duration) VALUES(?,?,?,?,?)',
                                    (identifier, str(media), str(tmp_path), 'standby-test', 100)).lastrowid
    library.set_setting('lan', {'enabled': True, 'port': 0})
    library.set_setting('lan_token', 'standby-test-token')
    library.close()
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    arguments = [sys.executable, '-m', 'lumen', '--background-no-tray', '--data-dir', str(directory)]
    process = subprocess.Popen(arguments, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    client = None
    try:
        def connected():
            if process.poll() is not None:
                raise AssertionError(process.communicate()[1].decode()[-2000:])
            try:
                value = RuntimeClient(directory, timeout=1)
                value.request('ping'); return value
            except (OSError, ValueError): return None
        client = wait_until(connected)
        state = client.request('status')
        assert state['lan']['running'] and not state['gui_running']
        port = state['lan']['port']
        opener = build_opener(ProxyHandler({}))
        def stream():
            request = Request(f'http://127.0.0.1:{port}/api/files/{file_id}/stream',
                              headers={'Authorization': 'Bearer standby-test-token', 'Range': 'bytes=123-1022'})
            with opener.open(request, timeout=2) as response:
                assert response.status == 206 and response.read() == content[123:1023]
        stream()
        # A GUI heartbeat/close never reconstructs or closes the LAN listener.
        client.request('poll', snapshot={'busy': True, 'remote': {'available': True}, 'closing': False})
        client.request('poll', snapshot={'busy': False, 'remote': {}, 'closing': True})
        assert client.request('status')['lan']['port'] == port
        stream()
        duplicate = subprocess.run(arguments, env=environment, capture_output=True, timeout=10)
        assert duplicate.returncode == 0, duplicate.stderr
        duplicate_serve = subprocess.run([sys.executable, '-m', 'lumen', '--serve', '--data-dir', str(directory)],
                                        env=environment, capture_output=True, timeout=10)
        assert duplicate_serve.returncode == 1 and b'already' in duplicate_serve.stderr
        assert process.poll() is None
        runtime = json.loads((directory / 'desktop-runtime.json').read_text())
        request = Request(f'http://127.0.0.1:{runtime["port"]}/control', b'{"action":"exit"}',
                          {'Authorization': 'Bearer incorrect'})
        with pytest.raises(HTTPError) as failure: opener.open(request, timeout=2)
        assert failure.value.code == 403 and process.poll() is None
        maps = Path(f'/proc/{process.pid}/maps')
        if maps.exists():
            assert not any(word in maps.read_text() for word in ('libQt6', 'libmpv'))
        client.request('exit')
        output, error = process.communicate(timeout=15)
        assert process.returncode == 0, error.decode()[-2000:]
        assert not (directory / 'desktop-runtime.json').exists()
        with pytest.raises(OSError): stream()
    finally:
        if process.poll() is None:
            try:
                if client: client.request('exit')
                process.communicate(timeout=10)
            except Exception:
                process.kill(); process.communicate(timeout=5)


def test_client_rejects_invalid_runtime_metadata(tmp_path):
    path = tmp_path / 'desktop-runtime.json'
    path.write_text(json.dumps({'port': '8097', 'token': 'x' * 64}))
    with pytest.raises(OSError): RuntimeClient(tmp_path)
    path.write_text(' ' * 4097)
    with pytest.raises(OSError): RuntimeClient(tmp_path)


def test_background_worker_uses_the_actual_application_entry(tmp_path):
    from lumen.background_service import command_for_worker
    library = Library(tmp_path / 'library'); library.close()
    result_path = tmp_path / 'result.json'
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run(command_for_worker('watch', tmp_path / 'library', tmp_path / 'cancel', result_path),
                            env=environment, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode()[-2000:]
    assert json.loads(result_path.read_text())['status'] == 'done'
