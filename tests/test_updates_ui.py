from dataclasses import asdict
import json
import threading
from pathlib import Path
import time
import pytest
from PySide6.QtCore import QEventLoop,QTimer
from lumen import updates
from lumen.ui import MainWindow
from test_desktop_updates import candidate,executable


def spin(app,seconds=.03):
    loop=QEventLoop();QTimer.singleShot(round(seconds*1000),loop.quit);loop.exec();app.processEvents()


def until(app,predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:spin(app)
    assert predicate()


@pytest.fixture
def window(qapp,tmp_path):
    window=MainWindow(tmp_path/'updates-ui');window.show()
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    yield window
    window._update_pending=False;window.close();until(qapp,lambda:not window._auxiliary_jobs and not window.jobs and not window.isVisible())


def test_check_and_download_keep_gui_responsive_and_auto_install_waits_for_idle(qapp,window,monkeypatch):
    entered=threading.Event();release=threading.Event();value=candidate();calls=[]
    def check(*args):
        assert threading.current_thread() is not threading.main_thread()
        entered.set();release.wait(4);return value
    monkeypatch.setattr(updates,'check',check);monkeypatch.setattr(updates,'can_install',lambda:True)
    controller=window.updater();until(qapp,lambda:not controller.restoring);controller.show()
    ticks=[];timer=QTimer(window);timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    controller.check();until(qapp,entered.is_set);spin(qapp,.1);assert len(ticks)>3 and controller.busy
    release.set();until(qapp,lambda:not controller.busy and not window._auxiliary_jobs);assert controller.candidate==value
    def download(candidate,directory,progress,cancelled,**kwargs):
        assert threading.current_thread() is not threading.main_thread()
        directory.mkdir(parents=True,exist_ok=True);path=directory/f'Lumen-Setup-{candidate.version}-x64.exe';path.write_bytes(executable());progress(len(executable()),len(executable()));return path
    monkeypatch.setattr(updates,'download',download);controller.download();until(qapp,lambda:controller.staged is not None and not window._auxiliary_jobs)
    # A queued import and a recently active Android playback session both defer updates.
    window.job_queue.append(('Queued import',None,None,'x',False));controller.option('install',True);controller.maybe_install();assert not controller.busy
    window.job_queue.clear()
    class Server:
        lock=threading.RLock();sessions={'s':{'time':10}};clock=staticmethod(lambda:11)
    window.lan_server=Server();assert not controller.idle();window.lan_server=None
    monkeypatch.setattr(updates,'launch_installer',lambda plan:calls.append(plan));original_close=window.close;monkeypatch.setattr(window,'close',lambda:calls.append('close'))
    controller.maybe_install();until(qapp,lambda:'close' in calls)
    assert list(controller.directory.glob('library-before-*.sqlite')) and window._update_pending
    assert isinstance(calls[0],dict) and calls[-1]=='close'
    window._update_pending=False;monkeypatch.setattr(window,'close',original_close)


def test_cached_update_recovers_without_network_and_failed_install_does_not_auto_retry(qapp,window,monkeypatch):
    value=candidate();directory=window.library.directory/'updates';directory.mkdir();path=directory/f'Lumen-Setup-{value.version}-x64.exe';path.write_bytes(executable())
    (directory/'staged.json').write_text(json.dumps(asdict(value)));(directory/'update-result.json').write_text(json.dumps({'version':value.version,'ok':False}))
    controller=window.updater();until(qapp,lambda:not controller.restoring and not window._auxiliary_jobs)
    assert controller.staged==path and controller.failed_version==value.version
    window.library.set_setting('updates:install',True);monkeypatch.setattr(controller,'install',lambda:pytest.fail('Must not retry a failed installation automatically'))
    controller.maybe_install();assert not controller.busy


def test_automatic_checks_respect_daily_interval_and_disabled_preference(qapp,window,monkeypatch):
    controller=window.updater();until(qapp,lambda:not controller.restoring and not window._auxiliary_jobs)
    calls=[];monkeypatch.setattr(controller,'check',lambda:calls.append(True))
    window.library.set_setting('updates:check',False);controller.startup();assert not calls
    window.library.set_setting('updates:check',True);window.library.set_setting('updates:last_check',time.time());controller.startup();assert not calls
    window.library.set_setting('updates:last_check',time.time()-86401);controller.startup();assert calls==[True]


def test_idle_probe_never_waits_for_busy_server_lock_or_lan_download(qapp,window):
    controller=window.updater();until(qapp,lambda:not controller.restoring and not window._auxiliary_jobs)
    class Server:
        lock=threading.RLock();sessions={};clock=staticmethod(lambda:0)
    server=Server();held=threading.Event();release=threading.Event()
    def hold():
        with server.lock:held.set();release.wait(3)
    thread=threading.Thread(target=hold);thread.start();held.wait(2);window.lan_server=server
    try:assert not controller.idle()
    finally:release.set();thread.join();window.lan_server=None
    window.task_budget.active=1;assert not controller.idle();window.task_budget.active=0
    class Downloads:
        lock=threading.Lock();active={'download':'job'}
    server.downloads=Downloads();window.lan_server=server
    try:assert not controller.idle()
    finally:window.lan_server=None
