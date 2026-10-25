"""Real writer contention, playback accounting and automatic stall evidence."""
import sqlite3
import time

import pytest
from PySide6.QtCore import QEventLoop,QTimer

from lumen.core import Library
from lumen.playback_journal import PlaybackJournal,PlaybackSession
from test_core import add_work


def wait_for(predicate,timeout=5):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:time.sleep(.01)
    assert predicate()


def test_opening_current_library_is_read_only_during_import_writer_lock(library):
    work=add_work(library,'Contended library')
    writer=sqlite3.connect(library.directory/'library.sqlite')
    writer.execute('BEGIN IMMEDIATE')
    try:
        started=time.monotonic()
        reopened=Library(library.directory,timeout=.15)
        assert time.monotonic()-started<.4
        assert reopened.work(work)['title']=='Contended library'
        assert reopened.db.total_changes==0
        reopened.close()
    finally:writer.rollback();writer.close()


def test_gui_write_fails_promptly_instead_of_waiting_30_seconds(library):
    work=add_work(library,'Short foreground wait')
    foreground=Library(library.directory,timeout=.15)
    writer=sqlite3.connect(library.directory/'library.sqlite')
    writer.execute('BEGIN IMMEDIATE')
    try:
        started=time.monotonic()
        with pytest.raises(sqlite3.OperationalError,match='locked'):foreground.update_personal(work,rating=8)
        assert time.monotonic()-started<.4
        assert foreground.work(work)['rating'] is None
    finally:writer.rollback();writer.close();foreground.close()


def test_playback_accumulates_during_lock_then_flushes_once_without_losing_last_sample(library):
    work=add_work(library,'Accounting under contention')
    file=library.work(work)['files'][0]
    writer=sqlite3.connect(library.directory/'library.sqlite')
    writer.execute('BEGIN IMMEDIATE')
    journal=PlaybackJournal(library.directory)
    clock=[0.0]
    try:
        started=time.monotonic()
        session=PlaybackSession(journal,file['id'],lambda:clock[0])
        session.tick(0,True)
        for second in range(1,602):
            clock[0]=second
            session.tick(second,True)
        clock[0]+=1;session.tick(900,True,seeking=True)
        clock[0]+=1;session.tick(902,True,rate=2)
        clock[0]+=1;session.tick(902,False)
        journal.duration(file['id'],1200)
        session.finish()
        assert time.monotonic()-started<.2
        with journal.condition:assert len(journal.pending)<=2
        assert not journal.stop()  # An in-flight transaction is not mistaken for an empty flush.
    finally:writer.rollback();writer.close()
    wait_for(journal.stop)
    saved=library.db.execute('SELECT watched,ended FROM sessions WHERE id=?',(session.id,)).fetchone()
    assert saved['watched']==602 and saved['ended']
    assert sum(row[0] for row in library.db.execute('SELECT watched FROM activity WHERE session_id=?',(session.id,)))==602
    media=library.work(work)['files'][0]
    assert media['position']==902 and media['duration']==1200


def test_player_event_loop_keeps_ticking_during_database_writer_lock(qapp,library,video_factory):
    from lumen.player import Player
    source=video_factory('Contention playback.mp4','blue',4)
    library.import_folder(source.parent,'movie')
    file=library.query()[0]['files'][0]
    player=Player(library)
    player.open_file(file)
    writer=sqlite3.connect(library.directory/'library.sqlite')
    writer.execute('BEGIN IMMEDIATE')
    ticks=[]
    timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    try:
        loop=QEventLoop();QTimer.singleShot(180,loop.quit);loop.exec()
        player.sample()
        player.duration_changed(4000)
        assert len(ticks)>=8
    finally:
        timer.stop();writer.rollback();writer.close();player.close()
    wait_for(player.playback_journal.stop)


def test_watchdog_records_gui_stack_only_after_threshold_and_rotates(qapp,tmp_path):
    from lumen.diagnostics import UiWatchdog
    clock=[10.0]
    watchdog=UiWatchdog(tmp_path,threshold=3,clock=lambda:clock[0],start=False)
    watchdog.check();assert not (tmp_path/'ui-hangs.log').exists()
    clock[0]=13.5;watchdog.check()
    path=tmp_path/'ui-hangs.log';content=path.read_text()
    assert 'Qt heartbeat delayed 3.50s' in content and 'GUI Python stack' in content
    assert 'test_watchdog_records_gui_stack' in content
    clock[0]=14;watchdog.check();assert path.read_text()==content
    watchdog.beat();watchdog.check();assert not watchdog.stalled
    path.write_text('x'*(4*1024*1024))
    clock[0]=18;watchdog.check()
    assert (tmp_path/'ui-hangs.log.1').stat().st_size==4*1024*1024
    assert path.stat().st_size<100000
    watchdog.stop()


def test_exit_with_long_writer_lock_preserves_then_recovers_last_playback_snapshot(library):
    import json
    work=add_work(library,'Recover after locked exit')
    file=library.work(work)['files'][0]
    writer=sqlite3.connect(library.directory/'library.sqlite');writer.execute('BEGIN IMMEDIATE')
    journal=PlaybackJournal(library.directory)
    clock=[0.0]
    try:
        session=PlaybackSession(journal,file['id'],lambda:clock[0]);session.tick(0,True)
        clock[0]=1;session.tick(1,True);session.finish()
        assert not journal.stop()
        journal.shutdown_deadline=time.monotonic()+.05
        wait_for(journal.stop)
        recovery=library.directory/'playback-pending.json'
        saved=json.loads(recovery.read_text())
        assert saved[0]['value']['watched']==1 and saved[0]['value']['ended']
        assert not library.db.execute('SELECT 1 FROM sessions WHERE id=?',(session.id,)).fetchone()
    finally:writer.rollback();writer.close()
    restored=PlaybackJournal(library.directory)
    restored.duration(file['id'],1000)
    wait_for(restored.stop)
    assert not recovery.exists()
    assert library.db.execute('SELECT watched,ended FROM sessions WHERE id=?',(session.id,)).fetchone()['watched']==1


def test_recovered_old_snapshot_never_overwrites_newer_same_session(library):
    import json
    work=add_work(library,'Newer snapshot wins');file=library.work(work)['files'][0]
    old={'file_id':file['id'],'started':'2026-10-25','ended':None,'watched':1,'days':{'2026-10-25':1},'position':1}
    path=library.directory/'playback-pending.json'
    path.write_text(json.dumps([{'key':['session','recovered'],'value':old}]))
    journal=PlaybackJournal(library.directory)
    journal.submit(('session','recovered'),{**old,'watched':5,'days':{'2026-10-25':5},'position':5,'ended':'2026-10-25'})
    wait_for(journal.stop)
    row=library.db.execute('SELECT * FROM sessions WHERE id=?',('recovered',)).fetchone()
    assert row['watched']==5 and row['ended']
    assert library.work(work)['files'][0]['position']==5 and not path.exists()
    assert not journal.latest_file


def test_unexpected_journal_error_retries_without_silently_killing_worker(library,monkeypatch):
    work=add_work(library,'Retry internal playback failure');file=library.work(work)['files'][0]
    journal=PlaybackJournal(library.directory);original=journal._write;attempts=[]
    def unexpected(*args):
        attempts.append(1)
        if len(attempts)==1:raise ValueError('injected one-off worker error')
        return original(*args)
    monkeypatch.setattr(journal,'_write',unexpected)
    session=PlaybackSession(journal,file['id']);session.finish()
    wait_for(journal.stop)
    assert len(attempts)>=2 and not journal.error
    assert library.db.execute('SELECT ended FROM sessions WHERE id=?',(session.id,)).fetchone()[0]
    assert not journal.latest_file


def test_end_of_media_while_writer_locked_is_async_and_keeps_completed_reset(qapp,library,video_factory):
    from PySide6.QtMultimedia import QMediaPlayer
    from lumen.player import Player
    source=video_factory('Completed under contention.mp4','blue',4)
    library.import_folder(source.parent,'movie');file=library.query()[0]['files'][0]
    player=Player(library);player.open_file(file)
    writer=sqlite3.connect(library.directory/'library.sqlite');writer.execute('BEGIN IMMEDIATE')
    try:
        started=time.monotonic();player.status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
        assert time.monotonic()-started<.2
    finally:writer.rollback();writer.close();player.close()
    wait_for(player.playback_journal.stop)
    saved=library.work(file['work_id'])['files'][0]
    assert saved['completed']==1 and saved['position']==0


def test_old_completion_cannot_override_new_playback_position_or_manual_reset(library):
    import json
    work=add_work(library,'File state order');file=library.work(work)['files'][0]
    writer=sqlite3.connect(library.directory/'library.sqlite');writer.execute('BEGIN IMMEDIATE')
    journal=PlaybackJournal(library.directory)
    try:
        old=PlaybackSession(journal,file['id']);old.tick(900,False);old.finish();journal.completed(file['id'])
        new=PlaybackSession(journal,file['id']);new.tick(5,True);new.finish()
    finally:writer.rollback();writer.close()
    wait_for(journal.stop)
    saved=library.work(work)['files'][0]
    assert saved['completed']==1 and saved['position']==5
    # A stale crash-recovery completion must respect an explicit user reset.
    library.set_watched(work,'reset')
    path=library.directory/'playback-pending.json'
    path.write_text(json.dumps([{'key':['file_state',file['id']],'value':{'file_id':file['id'],'completed':True,'position':0,'sampled':1}}]))
    restored=PlaybackJournal(library.directory);restored.duration(file['id'],1000);wait_for(restored.stop)
    assert library.work(work)['files'][0]['completed']==0


def test_slow_recovery_disk_write_never_holds_ui_submission_lock(library,monkeypatch):
    import threading
    work=add_work(library,'Slow disk close');file=library.work(work)['files'][0]
    writer=sqlite3.connect(library.directory/'library.sqlite');writer.execute('BEGIN IMMEDIATE')
    journal=PlaybackJournal(library.directory);entered=threading.Event();release=threading.Event();preserve=journal._preserve
    def slow():
        entered.set();release.wait(3);return preserve()
    monkeypatch.setattr(journal,'_preserve',slow)
    try:
        session=PlaybackSession(journal,file['id']);session.finish();journal.stop();journal.shutdown_deadline=time.monotonic()
        wait_for(entered.is_set)
        started=time.monotonic();assert not journal.stop();assert time.monotonic()-started<.05
    finally:release.set();writer.rollback();writer.close()
    wait_for(journal.stop)


def test_older_recovery_never_decreases_already_saved_accounting(library):
    import json
    work=add_work(library,'Idempotent recovery');file=library.work(work)['files'][0]
    value={'file_id':file['id'],'started':'2026-10-25','ended':'2026-10-25','watched':10,'days':{'2026-10-25':10},'position':10}
    journal=PlaybackJournal(library.directory);journal.submit(('session','stable'),value);wait_for(journal.stop)
    path=library.directory/'playback-pending.json'
    path.write_text(json.dumps([{'key':['session','stable'],'value':{**value,'watched':1,'days':{'2026-10-25':1},'position':1,'sampled':1,'ended':None}}]))
    restored=PlaybackJournal(library.directory);restored.duration(file['id'],1000);wait_for(restored.stop)
    saved=library.db.execute('SELECT watched,ended FROM sessions WHERE id=?',('stable',)).fetchone()
    assert saved['watched']==10 and saved['ended']
    assert library.db.execute('SELECT watched FROM activity WHERE session_id=?',('stable',)).fetchone()[0]==10
    assert library.work(work)['files'][0]['position']==10
