"""Real IPC, managed Qt windows and supervisor-owned service/lease lifetimes."""
import json
import threading
import time
from types import SimpleNamespace
from urllib.request import Request, build_opener, ProxyHandler

import pytest
from PySide6.QtCore import QEventLoop, QTimer, QThread

from lumen.core import ImportCancelled, Library
from lumen.desktop_client import GuiRuntimeClient
from lumen.desktop_runtime import DesktopRuntime, RuntimeClient, RUNTIME_FILE
from lumen.ui import MainWindow


def spin(app, seconds=.02):
    loop=QEventLoop();QTimer.singleShot(max(1,int(seconds*1000)),loop.quit);loop.exec();app.processEvents()


def until(app, condition, timeout=8):
    end=time.monotonic()+timeout
    while not condition() and time.monotonic()<end:spin(app)
    assert condition()


@pytest.fixture
def owner(tmp_path, monkeypatch):
    from lumen import image_isolation
    directory=tmp_path/'managed'
    library=Library(directory);library.set_setting('lan',{'enabled':True,'port':0});library.set_setting('remote_enabled',True);library.close()
    monkeypatch.setenv('LUMEN_BACKGROUND_SERVICE','1')
    monkeypatch.setattr(image_isolation,'_shutdown_event',None)
    runtime=DesktopRuntime(directory,tray=False,open_window=False)
    errors=[]
    def run():
        try:runtime.run()
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=run,name='TestDesktopOwner',daemon=True);thread.start()
    deadline=time.monotonic()+8
    while not (directory/RUNTIME_FILE).is_file() and time.monotonic()<deadline:time.sleep(.02)
    assert (directory/RUNTIME_FILE).is_file(),errors
    # The real GUI is hosted by this pytest Qt process instead of spawning another one.
    runtime.child=SimpleNamespace(poll=lambda:None)
    client=RuntimeClient(directory,timeout=3)
    yield runtime,directory,client
    runtime.child=None
    if thread.is_alive():
        try:client.request('exit')
        except OSError:runtime.stopping.set()
    thread.join(timeout=8)
    assert not thread.is_alive()
    assert not errors


def window_for(qapp,directory):
    client=GuiRuntimeClient(directory);window=MainWindow(directory,desktop_client=client)
    for timer in (window.scheduler,window.media_scheduler,window.inspect_scheduler,window.resource_scheduler,window.watch_scheduler):timer.stop()
    window.show();client.attach(window)
    until(qapp,lambda:not window.jobs and not window.job_queue and window._browse_job is None and not window._auxiliary_jobs)
    return window,client


def close_window(qapp,window,client):
    client.exit_requested=True;window.close();until(qapp,lambda:getattr(window,'_shutdown_complete',False));client.stop()


def lan_info(directory,status):
    library=Library(directory,initialize=False)
    try:token=library.setting('lan_token','')
    finally:library.close()
    request=Request(f"http://127.0.0.1:{status['lan']['port']}/api/info",headers={'Authorization':'Bearer '+token})
    with build_opener(ProxyHandler({})).open(request,timeout=3) as response:return json.load(response)


def test_managed_window_close_and_reopen_keep_real_lan_and_other_process_tasks(qapp,owner,monkeypatch):
    runtime,directory,wire=owner
    library=Library(directory,initialize=False);library.task('parent-task','background','running',{'title':'Owner task'});library.close()
    from lumen import server
    monkeypatch.setattr(server.LanServer,'__init__',lambda *args,**kwargs:pytest.fail('Managed GUI must not create a second LAN server'))
    window,client=window_for(qapp,directory)
    assert window.library.db.execute("SELECT status FROM tasks WHERE id='parent-task'").fetchone()[0]=='running'
    port=wire.request('status')['lan']['port'];assert lan_info(directory,wire.request('status'))['api_version']==1
    client.task_budget.set_paused(True)
    window.close();until(qapp,lambda:getattr(window,'_shutdown_complete',False))
    assert not client._thread.is_alive();assert wire.request('status')['lan']['port']==port
    assert wire.request('status')['budget']['paused']
    assert lan_info(directory,wire.request('status'))['api_version']==1
    wire.request('budget',paused=False)
    second,bridge=window_for(qapp,directory)
    try:assert second.lan_server and second.lan_server.port==port
    finally:close_window(qapp,second,bridge)


def test_remote_delivery_keeps_identity_time_and_gui_polling_stays_on_worker(qapp,owner):
    runtime,directory,wire=owner;window,client=window_for(qapp,directory)
    try:
        window.remote.timer.stop();calls=[];request=client._poll.request
        def observed(*args,**kwargs):calls.append(threading.get_ident());return request(*args,**kwargs)
        client._poll.request=observed
        before=time.monotonic();identifier=runtime.remote.submit({'action':'shutdown_cancel'});after=time.monotonic()
        until(qapp,lambda:not window.remote.pending.empty())
        item=window.remote.pending.get_nowait();assert item[0]==identifier;assert before<=item[1]<=after;assert item[2]=={'action':'shutdown_cancel'}
        window.remote.pending.put_nowait(item);window.remote.pump();client._capture()
        until(qapp,lambda:runtime.remote.state().get('last_command',{}).get('id')==identifier)
        assert runtime.remote.state()['last_command']['ok']
        for _ in range(20):window.sync_playback_budget();client._capture()
        until(qapp,lambda:bool(calls));assert all(thread!=threading.get_ident() for thread in calls)
        assert wire.request('status')['lan']['running']
    finally:close_window(qapp,window,client)


def test_normal_close_hides_active_job_without_cancelling_and_parent_quit_stops_it(qapp,owner):
    runtime,directory,wire=owner;window,client=window_for(qapp,directory);started=threading.Event();cancelled=threading.Event();interruptions=[]
    def work(library,progress):
        started.set()
        try:
            while not progress.cancelled():time.sleep(.02)
            raise ImportCancelled('Stopped')
        finally:
            interruptions.append(QThread.currentThread().isInterruptionRequested())
            cancelled.set()
    try:
        window.run_job('Managed import',work)
        until(qapp,started.is_set);worker=window.jobs[0]
        window.close();spin(qapp,.1)
        assert not window.isVisible() and window._tray_requested
        assert not window._closing and not worker.isInterruptionRequested() and not cancelled.is_set()
        assert wire.request('status')['lan']['running']
        wire.request('exit')
        until(qapp,lambda:getattr(window,'_shutdown_complete',False))
        assert cancelled.is_set() and client.exit_requested
        assert interruptions==[True] and not window.jobs
    finally:
        if not getattr(window,'_shutdown_complete',False):close_window(qapp,window,client)


def test_closing_a_used_player_allows_idle_gui_to_release(qapp,owner,video_factory):
    runtime,directory,wire=owner;window,client=window_for(qapp,directory)
    try:
        path=video_factory('Managed-player.mp4','blue',2);window.library.import_folder(path.parent,'movie');file=window.library.query()[0]['files'][0]
        window.player.open_file(file);assert client.gui_active(window)
        window.player.close();until(qapp,lambda:window.player.session is None)
        assert window.player.file is not None,'The regression requires the historical file pointer to remain'
        assert not client.gui_active(window)
        window.close();until(qapp,lambda:getattr(window,'_shutdown_complete',False))
        assert wire.request('status')['lan']['running']
    finally:
        if not getattr(window,'_shutdown_complete',False):close_window(qapp,window,client)


def test_runtime_budget_cancels_waiting_lease_and_yields_background_capacity(qapp,owner):
    runtime,directory,wire=owner;client=GuiRuntimeClient(directory);budget=client.task_budget
    until(qapp,lambda:wire.request('lease',op='acquire',identifier='other-worker',resource='cpu',background=False)['acquired'])
    cancel=threading.Event();errors=[]
    def waiting():
        try:budget.acquire(cancel.is_set,resource='disk')
        except ImportCancelled as error:errors.append(error)
    worker=threading.Thread(target=waiting);worker.start();spin(qapp,.2);cancel.set();worker.join(timeout=3)
    assert not worker.is_alive() and len(errors)==1
    wire.request('lease',op='release',identifier='other-worker')
    until(qapp,lambda:wire.request('status')['budget']['active']==0)
    acquired=threading.Event();checkpoint=threading.Event();finished=threading.Event();cancel.clear()
    def background():
        try:
            budget.acquire(cancel.is_set,resource='cpu',background=True);acquired.set();checkpoint.wait(3);budget.checkpoint(cancel.is_set)
        except ImportCancelled:pass
        finally:budget.release();finished.set()
    worker=threading.Thread(target=background);worker.start();assert acquired.wait(3);budget.set_playback(True);checkpoint.set()
    until(qapp,lambda:wire.request('status')['budget']['active']==0)
    until(qapp,lambda:wire.request('lease',op='acquire',identifier='foreground',resource='cpu',background=False)['acquired'])
    cancel.set();assert finished.wait(3);worker.join(timeout=1);wire.request('lease',op='release',identifier='foreground')
    budget.set_limit(2);assert wire.request('status')['budget']['limit']==2
    client.stop();until(qapp,lambda:wire.request('status')['budget']['active']==0)


def test_quit_ack_requires_handled_nonce_and_show_ack_only_after_display(qapp,owner,monkeypatch):
    runtime,directory,wire=owner;window,client=window_for(qapp,directory)
    try:
        # A delayed GUI delivery with old closing=False never cancels a parent exit.
        client.timer.stop();client._stopped.set();client._thread.join(timeout=2);client._stopped.clear();client._thread=None
        wire.request('exit');first=wire.request('status');time.sleep(1.1)
        wire.request('poll',snapshot={'remote':{},'closing':False})
        assert wire.request('status')['exit_requested']
        actual_close=window.close;monkeypatch.setattr(window,'close',lambda:False)
        client._deliver({'events':['quit'],'status':first});client._capture()
        with client._state_lock:snapshot=dict(client._snapshot)
        assert snapshot['exit_cancelled'] and snapshot['exit_request_id']==first['exit_request_id']
        wire.request('poll',snapshot=snapshot);assert not wire.request('status')['exit_requested']
        client._deliver({'status':wire.request('status')});assert not client.exit_requested and not client._quit_handled
        window._tray_requested=True;window.hide();wire.request('open');show=wire.request('status');client._deliver({'events':['show'],'status':show});assert window.isVisible() and not window._tray_requested
        assert client._snapshot['show_ack_id']==show['show_request_id']
        monkeypatch.setattr(window,'close',actual_close)
        # A new exit cannot be revoked by the old cancellation acknowledgement.
        wire.request('exit');second=wire.request('status');assert second['exit_request_id']!=first['exit_request_id']
        wire.request('poll',snapshot=snapshot);assert wire.request('status')['exit_requested']
        client._deliver({'events':['quit'],'status':second});until(qapp,lambda:getattr(window,'_shutdown_complete',False))
    finally:
        if not getattr(window,'_shutdown_complete',False):close_window(qapp,window,client)


def test_full_or_closing_gui_keeps_commands_in_the_bounded_owner_mailbox(qapp,owner):
    runtime,directory,wire=owner;window,client=window_for(qapp,directory)
    try:
        window.remote.timer.stop();window.remote.pump()
        for index in range(32):window.remote.pending.put_nowait((f'held-{index}',time.monotonic(),{'action':'shutdown_cancel'}))
        client._capture();until(qapp,lambda:runtime.gui_snapshot.get('accept_commands') is False and runtime.gui_snapshot.get('remote',{}).get('available') is True)
        before=time.monotonic();identifier=runtime.remote.submit({'action':'shutdown_cancel'});after=time.monotonic()
        spin(qapp,.65);assert runtime.remote.pending.qsize()==1;assert not client._pending_commands
        window.remote.pending.get_nowait();client._capture();until(qapp,lambda:runtime.remote.pending.empty())
        until(qapp,window.remote.pending.full)
        delivered=[]
        while not window.remote.pending.empty():delivered.append(window.remote.pending.get_nowait())
        command=next(item for item in delivered if item[0]==identifier);assert before<=command[1]<=after;assert command[2]=={'action':'shutdown_cancel'}
        window._closing=True;client._capture();until(qapp,lambda:runtime.gui_snapshot.get('accept_commands') is False)
        closing_id=runtime.remote.submit({'action':'shutdown_cancel'});spin(qapp,.65)
        assert runtime.remote.pending.qsize()==1
        with runtime.remote.pending.mutex:assert runtime.remote.pending.queue[0]['id']==closing_id
        assert not client._pending_commands
        window._closing=False
    finally:
        window._closing=False
        close_window(qapp,window,client)
