import json
import shutil
from pathlib import Path
from unittest.mock import Mock
from lumen import core, nfo


def test_fast_import_does_not_hash_probe_or_decode_unique_video(library,tmp_path,monkeypatch,qapp):
    from PySide6.QtGui import QImage,QColor
    folder=tmp_path/'media';folder.mkdir();video=folder/'Movie.mp4'
    with video.open('wb') as stream:
        stream.seek(64*1024*1024-1);stream.write(b'x')
    video.with_suffix('.nfo').write_text('<movie><title>Fast title</title><resume><position>12</position></resume></movie>',encoding='utf-8')
    image=QImage(100,150,QImage.Format.Format_RGB32);image.fill(QColor('red'));image.save(str(folder/'poster.png'))
    blocked=Mock(side_effect=AssertionError('Heavy operation during fast import'))
    monkeypatch.setattr(core,'fingerprint',blocked);monkeypatch.setattr(core,'probe',blocked);monkeypatch.setattr(core,'thumbnail',blocked)
    result=library.import_folder(folder,'movie',fast=True)
    assert result['imported']==1 and result['errors']==[]
    blocked.assert_not_called()
    work=library.query()[0]
    assert work['title']=='Fast title' and Path(work['thumbnail']).is_file()
    assert work['files'][0]['duration']==0 and work['files'][0]['position']==12
    monkeypatch.setattr(core,'probe',lambda path:20)
    result=library.enrich_pending()
    assert result['completed']==1 and result['errors']==[]
    assert library.work(work['id'])['files'][0]['duration']==20
    blocked.assert_not_called()  # Local poster avoids video screenshot decoding.


def test_sample_collision_is_not_a_duplicate(library,tmp_path):
    folder=tmp_path/'media';folder.mkdir()
    first=folder/'First.mp4';second=folder/'Second.mp4'
    first.write_bytes(b'0'*(1024*1024))
    data=bytearray(first.read_bytes());data[250000]=ord('1');second.write_bytes(data)
    assert core.quick_fingerprint(first)==core.quick_fingerprint(second)
    result=library.import_folder(folder,'movie',fast=True)
    assert result['imported']==2 and result['duplicates']==0 and not result['errors']
    copies=tmp_path/'copies';copies.mkdir();shutil.copy2(first,copies/'Renamed.mp4')
    result=library.import_folder(copies,'movie',fast=True)
    assert result['duplicates']==1 and result['imported']==0
    assert len(library.query())==2


def test_unchanged_rescan_skips_content_but_changed_nfo_is_applied(library,tmp_path,monkeypatch):
    folder=tmp_path/'media';folder.mkdir();video=folder/'Movie.mp4';video.write_bytes(b'video fixture')
    sidecar=video.with_suffix('.nfo');sidecar.write_text('<movie><title>Before</title></movie>',encoding='utf-8')
    library.import_folder(folder,'movie',fast=True)
    work=library.query()[0];library.update_personal(work['id'],rating=9,favorite=True)
    read=Mock(wraps=nfo.read);quick=Mock(wraps=core.quick_fingerprint)
    monkeypatch.setattr(nfo,'read',read);monkeypatch.setattr(core,'quick_fingerprint',quick)
    result=library.import_folder(folder,'movie',fast=True)
    assert result['duplicates']==1 and result.get('nfo_updated',0)==0
    read.assert_not_called();quick.assert_not_called()
    sidecar.write_text('<movie><title>After updated title</title></movie>',encoding='utf-8')
    result=library.import_folder(folder,'movie',fast=True)
    assert result['nfo_updated']==1 and read.call_count==1
    quick.assert_not_called()
    updated=library.work(work['id'])
    assert updated['title']=='After updated title' and updated['rating']==9 and updated['favorite']==1
    old_digest=updated['files'][0]['digest']
    video.write_bytes(b'changed video contents')
    library.import_folder(folder,'movie',fast=True)
    assert quick.call_count==1 and library.work(work['id'])['files'][0]['digest']!=old_digest


def test_queue_survives_restart_and_records_failure(library,tmp_path,monkeypatch):
    folder=tmp_path/'media';folder.mkdir();(folder/'Movie.mp4').write_bytes(b'invalid video')
    library.import_folder(folder,'movie',fast=True)
    reopened=core.Library(library.directory)
    try:
        monkeypatch.setattr(core,'probe',Mock(side_effect=ValueError('invalid video')))
        result=reopened.enrich_pending()
        assert len(result['errors'])==1
        assert reopened.db.execute('SELECT pending FROM import_cache').fetchone()[0]==-1
        task=reopened.db.execute("SELECT status,error FROM tasks WHERE kind='media'").fetchone()
        assert task['status']=='failed' and 'invalid video' in task['error']
        assert reopened.enrich_pending()['errors']==[]
    finally:reopened.close()


def test_fast_and_full_imports_share_duplicate_detection(library,tmp_path,video_factory):
    original=video_factory('Original.mp4')
    library.import_folder(original.parent,'movie')
    copies=tmp_path/'copies';copies.mkdir();shutil.copy2(original,copies/'Copy.mp4')
    assert library.import_folder(copies,'movie',fast=True)['duplicates']==1
    second=video_factory('Second.mp4','green')
    assert library.import_folder(second.parent,'movie',fast=True)['imported']==1
    shutil.copy2(second,copies/'Another copy.mp4')
    result=library.import_folder(copies,'movie')
    assert result['duplicates']==2 and result['imported']==0


def test_background_generates_frame_when_thumbnail_mode_requested(library,video_factory):
    video=video_factory('Frame.mp4')
    library.import_folder(video.parent,'movie',fast=True)
    library.set_setting('view_mode','thumbnail')
    result=library.enrich_pending()
    assert result['completed']==1 and not result['errors']
    work=library.query()[0]
    assert work['files'][0]['duration']>0 and Path(work['thumbnail']).is_file()


def test_fast_imported_video_can_play_before_background_probe(qapp,library,video_factory):
    from lumen.player import Player
    from PySide6.QtCore import QEventLoop,QTimer
    from PySide6.QtMultimedia import QMediaPlayer
    video=video_factory('Immediate.mp4','blue',10)
    library.import_folder(video.parent,'movie',fast=True)
    file=library.query()[0]['files'][0]
    assert file['duration']==0
    player=Player(library);frames=[]
    player.video.videoSink().videoFrameChanged.connect(lambda frame:frames.append(frame.isValid()))
    player.open_file(file)
    loop=QEventLoop();QTimer.singleShot(1200,loop.quit);loop.exec()
    assert player.media.error()==QMediaPlayer.Error.NoError
    assert any(frames)
    assert library.work(file['work_id'])['files'][0]['duration']>9
    player.close()


def test_cancel_scan_keeps_committed_files_and_rescan_continues(library,tmp_path):
    folder=tmp_path/'media';folder.mkdir()
    (folder/'A.mp4').write_bytes(b'first file');(folder/'B.mp4').write_bytes(b'second file')
    stop=[False]
    def progress(done,total,message):
        if done==1:stop[0]=True
    result=library.import_folder(folder,'movie',progress,fast=True,cancelled=lambda:stop[0])
    assert result['cancelled'] and result['imported']==1 and result['errors']==[]
    assert len(library.query())==1
    assert library.db.execute("SELECT status FROM tasks WHERE kind='import'").fetchone()[0]=='cancelled'
    result=library.import_folder(folder,'movie',fast=True)
    assert result['duplicates']==1 and result['imported']==1
    assert len(library.query())==2 and len(list(folder.glob('*.mp4')))==2


def test_cancel_background_preserves_pending_queue(library,tmp_path):
    folder=tmp_path/'media';folder.mkdir();(folder/'A.mp4').write_bytes(b'file')
    library.import_folder(folder,'movie',fast=True)
    result=library.enrich_pending(cancelled=lambda:True)
    assert result['cancelled'] and result['errors']==[]
    assert library.db.execute('SELECT pending FROM import_cache').fetchone()[0]==1
    assert library.db.execute("SELECT status FROM tasks WHERE kind='media'").fetchone()[0]=='cancelled'


def test_running_media_process_can_be_interrupted():
    import sys,time,pytest
    start=time.monotonic()
    with pytest.raises(core.ImportCancelled):
        core.media_process([sys.executable,'-c','import time; time.sleep(10)'],20,lambda:time.monotonic()-start>.15)
    assert time.monotonic()-start<3


def test_close_window_cancels_import_without_losing_library(qapp,tmp_path):
    import time
    from PySide6.QtCore import QEventLoop,QTimer
    from lumen.ui import MainWindow
    window=MainWindow(tmp_path/'closing');window.show()
    entered=[]
    def work(lib,progress):
        lib.set_setting('saved-before-close',True);entered.append(True)
        while not progress.cancelled():time.sleep(.01)
        return {'cancelled':True}
    window.run_job('快速导入',work)
    loop=QEventLoop();QTimer.singleShot(100,loop.quit);loop.exec()
    assert entered
    window.close()
    deadline=time.monotonic()+3
    while window.isVisible() and time.monotonic()<deadline:
        loop=QEventLoop();QTimer.singleShot(20,loop.quit);loop.exec()
    assert not window.isVisible() and not window.jobs
    reopened=core.Library(tmp_path/'closing')
    assert reopened.setting('saved-before-close') is True
    reopened.close()
