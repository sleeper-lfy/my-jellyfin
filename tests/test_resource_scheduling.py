import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from lumen.core import ImportCancelled
from lumen.task_journal import TaskBudget


def until(condition):
    deadline=time.monotonic()+3
    while not condition() and time.monotonic()<deadline:time.sleep(.005)
    assert condition()


def test_resource_lanes_serialize_disk_but_allow_cpu_and_network():
    budget=TaskBudget(3);gate=threading.Event();disk=threading.Event();cpu=threading.Event();network=threading.Event()
    def work(resource,entered):
        budget.acquire(resource=resource)
        try:entered.set();assert gate.wait(3)
        finally:budget.release()
    with ThreadPoolExecutor(4) as pool:
        budget.acquire(resource='disk')
        futures=[pool.submit(work,'disk',disk),pool.submit(work,'cpu',cpu),pool.submit(work,'network',network)]
        try:
            assert cpu.wait(2) and network.wait(2)
            assert not disk.is_set() and budget.active==3
        finally:budget.release();gate.set()
        for future in futures:future.result(3)
    assert disk.is_set() and budget.active==0


def test_playback_yields_running_automation_and_manual_work_uses_freed_slot():
    budget=TaskBudget(1);entered=threading.Event();checkpoint=threading.Event();resumed=threading.Event()
    def automatic():
        budget.acquire(resource='disk',background=True)
        try:
            entered.set();assert checkpoint.wait(3)
            budget.checkpoint();resumed.set()
        finally:budget.release()
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(automatic);assert entered.wait(2)
        budget.set_playback(True);checkpoint.set()
        until(lambda:budget.active==0)
        budget.acquire(resource='disk')
        try:assert not resumed.is_set() and budget.active==1
        finally:budget.release()
        assert not resumed.is_set()
        budget.set_playback(False);future.result(3)
    assert resumed.is_set() and budget.active==0


def test_manual_waiter_precedes_automatic_and_cancelled_waiter_does_not_leak():
    budget=TaskBudget(1);order=[];cancel=threading.Event()
    def work(name,background):
        budget.acquire(cancel.is_set if name=='cancel' else None,background=background)
        try:order.append(name)
        finally:budget.release()
    with ThreadPoolExecutor(3) as pool:
        budget.acquire()
        automatic=pool.submit(work,'automatic',True);until(lambda:len(budget.waiters)==1)
        manual=pool.submit(work,'manual',False);until(lambda:len(budget.waiters)==2)
        stopped=pool.submit(work,'cancel',False);until(lambda:len(budget.waiters)==3)
        cancel.set()
        with pytest.raises(ImportCancelled):stopped.result(2)
        budget.release();manual.result(2);automatic.result(2)
    assert order==['manual','automatic'] and budget.active==0 and not budget.waiters


def test_cancel_parked_automatic_releases_its_lease():
    budget=TaskBudget(1);ready=threading.Event();checkpoint=threading.Event();cancel=threading.Event()
    def work():
        budget.acquire(background=True)
        try:ready.set();checkpoint.wait(2);budget.checkpoint(cancel.is_set)
        finally:budget.release()
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(work);assert ready.wait(2)
        budget.set_playback(True);checkpoint.set();until(lambda:budget.active==0)
        cancel.set()
        with pytest.raises(ImportCancelled):future.result(2)
    budget.set_playback(False);budget.acquire();budget.release()
    assert budget.active==0 and not budget.waiters


def test_playback_queue_still_starts_manual_jobs(qapp,tmp_path):
    from lumen.ui import MainWindow
    from test_pc_stability import until as qt_until
    window=MainWindow(tmp_path/'resource-queue');window.show()
    for timer in (window.resource_scheduler,window.scheduler,window.media_scheduler,window.watch_scheduler):timer.stop()
    automatic=threading.Event();manual=threading.Event()
    try:
        window.task_budget.set_playback(True)
        window.run_job('automatic',lambda lib,p:automatic.set(),background=True)
        window.run_job('manual',lambda lib,p:manual.set())
        qt_until(qapp,manual.is_set)
        assert not automatic.is_set()
        window.task_budget.set_playback(False);window.start_queued_jobs()
        qt_until(qapp,automatic.is_set);qt_until(qapp,lambda:not window.jobs)
    finally:
        window.stop_jobs();window.close();qt_until(qapp,lambda:not window.jobs and not window.isVisible())


def test_media_process_finishes_before_cooperative_yield():
    import sys
    from lumen.core import media_process
    calls=[]
    def cancelled():calls.append('boundary');return False
    cancelled.process_cancelled=lambda:False
    result=media_process([sys.executable,'-c','import time; time.sleep(.15); print("done")'],2,cancelled)
    assert result.stdout.strip()==b'done' and calls==['boundary']


def test_recent_mobile_playback_yields_but_stale_or_paused_session_does_not(qapp,tmp_path):
    from types import SimpleNamespace
    from lumen.ui import MainWindow
    from test_pc_stability import until as qt_until
    window=MainWindow(tmp_path/'mobile-budget')
    try:
        state={'playing':True,'time':98}
        window.lan_server=SimpleNamespace(clock=lambda:100,sessions={'mobile':state})
        window.sync_playback_budget();assert window.task_budget.playback
        state['playing']=False;window.sync_playback_budget();assert not window.task_budget.playback
        state.update(playing=True,time=90);window.sync_playback_budget();assert not window.task_budget.playback
    finally:
        window.lan_server=None;window.close();qt_until(qapp,lambda:not window.isVisible() and not window.jobs)


def test_running_automatic_job_releases_capacity_for_manual_job(qapp,tmp_path):
    from lumen.ui import MainWindow
    from test_pc_stability import until as qt_until
    window=MainWindow(tmp_path/'yield-running');window.show()
    for timer in (window.resource_scheduler,window.scheduler,window.media_scheduler,window.watch_scheduler):timer.stop()
    entered=threading.Event();boundary=threading.Event();resumed=threading.Event();manual=threading.Event()
    def automatic(lib,progress):
        entered.set();assert boundary.wait(3)
        progress(1,2,'safe boundary');resumed.set();return {}
    try:
        window.run_job('automatic',automatic,background=True)
        qt_until(qapp,entered.is_set);window.task_budget.set_playback(True);boundary.set()
        qt_until(qapp,lambda:window.task_budget.active==0)
        window.run_job('manual',lambda lib,p:manual.set())
        qt_until(qapp,manual.is_set);assert not resumed.is_set()
        window.task_budget.set_playback(False);window.start_queued_jobs()
        qt_until(qapp,resumed.is_set);qt_until(qapp,lambda:not window.jobs)
    finally:
        boundary.set();window.stop_jobs();window.close();qt_until(qapp,lambda:not window.jobs and not window.isVisible())
