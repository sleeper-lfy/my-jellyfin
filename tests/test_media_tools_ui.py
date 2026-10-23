import json
import threading
import time
import httpx
import pytest
from PySide6.QtCore import QEventLoop,QTimer
from lumen.ui import MainWindow
from lumen.media_tools import preferences,add_bookmark
from lumen.remote import validate_command


def spin(app,seconds=.05):
    loop=QEventLoop();QTimer.singleShot(int(seconds*1000),loop.quit);loop.exec();app.processEvents()


def until(app,predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:spin(app,.02)
    assert predicate()


@pytest.fixture
def window(qapp,tmp_path):
    value=MainWindow(tmp_path/'new-tools');value.show()
    for timer in (value.media_scheduler,value.scheduler,value.watch_scheduler,value.remote.timer):timer.stop()
    yield value
    value.close();until(qapp,lambda:not value.jobs and not value.isVisible())


def test_subtitle_offset_size_position_and_file_memory(qapp,window,video_factory):
    video=video_factory('Subtitles.mp4','blue',5);video.with_suffix('.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nExample caption\n',encoding='utf-8')
    window.library.import_folder(video.parent,'movie');file=window.library.query()[0]['files'][0];player=window.player
    player.open_file(file);spin(qapp,.3);player.media.pause()
    player.subtitle_delay.setValue(1);player.subtitle_size.setValue(30);player.subtitle_position.setValue(75)
    player.position_changed(500);assert player.caption.text()==''
    player.position_changed(1500);assert 'Example caption' in player.caption.text()
    assert '30px' in player.caption.styleSheet()
    assert player.overlay.rect().contains(player.caption.geometry())
    assert preferences(window.library,file['id'])['subtitle_delay']==1
    report=json.dumps(player.diagnostics(),default=str)
    assert str(video) not in report and 'token' not in report
    player.close();player.open_file(file);spin(qapp,.2)
    assert player.subtitle_delay.value()==1 and player.subtitle_size.value()==30
    player.close()


def test_details_bookmarks_jump_without_marking_watched(qapp,window,video_factory):
    window.library.import_folder(video_factory('Jump.mp4','blue',6).parent,'movie');work=window.library.query()[0];file=work['files'][0]
    window.navigate('movie');window.open_details(work['id'],fetch=False)
    detail=window.detail_page;assert detail.bookmark_list.isHidden()
    mark=add_bookmark(window.library,file['id'],3,'Jump here','A scene')
    detail.refresh_bookmarks();assert detail.bookmark_list.count()==1
    detail.bookmark_list.itemDoubleClicked.emit(detail.bookmark_list.item(0));spin(qapp,.4)
    assert window.player.file['id']==file['id'] and window.player.media.position()>=2900
    assert window.library.stats()['valid']==0
    window.player.close()


def test_task_queue_pause_cancel_and_concurrency_limit(qapp,window):
    events=[];started=threading.Event();release=threading.Event()
    def first(lib,progress):
        events.append('first');started.set()
        while not release.is_set():
            if progress.cancelled():return {'cancelled':True}
            progress(1,10,'current-file');time.sleep(.01)
        events.append('first-done');return {'done':True}
    window.pause_jobs(True);window.run_job('first task',first);window.run_job('second task',lambda lib,p:events.append('second'))
    assert not window.jobs and len(window.job_queue)==2
    window.pause_jobs(False);until(qapp,started.is_set);assert len(window.jobs)==1 and len(window.job_queue)==1
    window.pause_jobs(True);spin(qapp,.05);assert events==['first']
    window.pause_jobs(False);release.set();until(qapp,lambda:not window.jobs and not window.job_queue)
    assert events==['first','first-done','second']
    until(qapp,lambda:window.library.db.execute("SELECT COUNT(*) FROM tasks WHERE kind='background' AND status='done'").fetchone()[0]==2)
    window.pause_jobs(True);window.run_job('cancel queued',lambda lib,p:events.append('unexpected'));window.stop_jobs()
    assert not window.job_queue and 'unexpected' not in events
    window.pause_jobs(False)


def test_task_progress_never_waits_for_sqlite_writer_on_gui_thread(qapp,window):
    locked=threading.Event();ticks=[]
    def slow_transaction(lib,progress):
        with lib.db:
            lib.db.execute("INSERT OR REPLACE INTO settings VALUES ('held-lock','true')")
            locked.set();progress(1,2,'holding writer');time.sleep(.35)
        return {'done':True}
    timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
    window.run_job('writer test',slow_transaction);until(qapp,lambda:not window.jobs)
    timer.stop();assert locked.is_set() and len(ticks)>15


@pytest.mark.parametrize('body',[{'action':'shell','value':'x'},{'action':'volume','value':101},{'action':'jump','value':float('nan')},{'action':'open','work_id':True},{'action':'pause','path':'secret'}])
def test_remote_rejects_invalid_or_arbitrary_commands(body):
    with pytest.raises(ValueError):validate_command(body)


def test_authenticated_phone_commands_execute_only_when_gui_pumps(qapp,window,video_factory):
    window.library.import_folder(video_factory('Remote.mp4','blue',20).parent,'movie');work=window.library.query()[0]
    window.library.set_setting('remote_enabled',True);window.apply_lan(True,0);server=window.lan_server
    # The HTTP thread may enqueue, but cannot touch any Qt player object.
    with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
        assert client.post('/api/remote',headers={'Authorization':''},json={'action':'pause'}).status_code==401
        response=client.post('/api/remote',json={'action':'open','work_id':work['id']});assert response.status_code==202
        assert not window.player.isVisible();window.remote.pump();spin(qapp,.4)
        assert window.player.file['work_id']==work['id']
        for command in ({'action':'pause'},{'action':'volume','value':23},{'action':'seek','value':8}):
            assert client.post('/api/remote',json=command).status_code==202
            window.remote.pump();spin(qapp,.1)
        window.remote.pump();state=client.get('/api/remote').json()
        assert state['volume']==23 and not state['playing'] and 7.9<=state['position']<=8.1
        assert str(window.library.directory) not in json.dumps(state) and server.token not in json.dumps(state)
        assert client.post('/api/remote',json={'action':'volume','value':900}).status_code==400
        window.library.set_setting('remote_enabled',False)
        assert client.post('/api/remote',json={'action':'play'}).status_code==403
    window.player.close()
