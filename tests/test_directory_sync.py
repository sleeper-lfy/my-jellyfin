import os
from pathlib import Path
from PySide6.QtWidgets import QPushButton
from lumen.core import WatchSession
from lumen.directory_sync import scan_directories,remove_missing
from lumen.library_tools_ui import LibraryTools
from lumen.ui import MainWindow


def video(root,name):
    root.mkdir(parents=True,exist_ok=True);path=root/name;path.write_bytes(name.encode());os.utime(path,(1,1));return path


def test_refresh_imports_new_movies_and_removes_only_confirmed_missing(library,tmp_path):
    root=tmp_path/'movies';old=video(root,'Old.mp4');other=video(tmp_path/'elsewhere','Other.mp4')
    library.import_folder(root,'movie',fast=True);library.import_folder(other.parent,'movie',fast=True)
    old_id=library.query({'folder':str(root)})[0]['id'];old.unlink();new=video(root,'New.mp4')
    report=scan_directories(library,[{'path':str(root),'kind':'movie'}])
    assert report['imported']==1 and len(report['missing'])==1
    assert library.work(old_id)  # No silent deletion before confirmation.
    assert remove_missing(library,report['missing'])=={'removed':1,'skipped':0}
    assert {work['title'] for work in library.query()}=={'New','Other'}
    assert new.is_file() and other.is_file()


def test_refresh_series_finds_whole_new_show_and_new_season(library,tmp_path):
    root=tmp_path/'shows';video(root/'Show'/'Season 1','Show.S01E01.mp4')
    config={'path':str(root),'kind':'series'}
    assert scan_directories(library,[config])['imported']==1
    video(root/'Show'/'Season 2','Show.S02E01.mp4');video(root/'Another'/'Season 1','Another.S01E01.mp4')
    assert scan_directories(library,[config])['imported']==2
    works=library.query({'kinds':['series']})
    assert len(works)==2 and sorted(len(work['files']) for work in works)==[1,2]
    assert scan_directories(library,[config])['imported']==0


def test_offline_or_inaccessible_root_never_proposes_removal(library,tmp_path,monkeypatch):
    root=tmp_path/'movies';video(root,'One.mp4');library.import_folder(root,'movie',fast=True)
    root.rename(tmp_path/'disconnected')
    result=scan_directories(library,[{'path':str(root),'kind':'movie'}])
    assert len(result['offline'])==1 and result['missing']==[] and library.query()
    (tmp_path/'disconnected').rename(root)
    def blocked(*args,**kwargs):raise PermissionError('no access')
    monkeypatch.setattr('lumen.directory_sync.scan_tree',blocked)
    result=scan_directories(library,[{'path':str(root),'kind':'movie'}])
    assert result['missing']==[] and len(result['offline'])==1


def test_confirmation_rechecks_reappeared_file_and_disconnected_root(library,tmp_path):
    root=tmp_path/'movies';file=video(root,'One.mp4');library.import_folder(root,'movie',fast=True);file.unlink()
    report=scan_directories(library,[{'path':str(root),'kind':'movie'}])
    video(root,'One.mp4')
    assert remove_missing(library,report['missing'])=={'removed':0,'skipped':1}
    file.unlink();root.rename(tmp_path/'offline')
    assert remove_missing(library,report['missing'])=={'removed':0,'skipped':1}
    assert library.query()


def test_refresh_waits_for_writing_files_and_queues_configured_ingestion(library,tmp_path):
    root=tmp_path/'vr';file=video(root,'ABC-123.mp4');os.utime(file,(100,100))
    config={'path':str(root),'kind':'vr','plugin':'film-provider','destination':''}
    result=scan_directories(library,[config],clock=lambda:105)
    assert result['waiting']==1 and result['imported']==0
    result=scan_directories(library,[config],clock=lambda:130)
    assert result['imported']==1
    assert library.db.execute("SELECT 1 FROM tasks WHERE kind='ingest' AND status='queued'").fetchone()


def test_category_filter_edits_correct_directory_and_refreshes_saved_scope(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        configs=[{'path':str(tmp_path/'movies'),'kind':'movie'},{'path':str(tmp_path/'shows'),'kind':'series'}]
        window.library.set_setting('watched_folders',configs);window.navigate('series')
        dialog=LibraryTools(window)
        assert dialog.list.count()==1 and dialog.selected_index()==-1
        dialog.list.setCurrentRow(0);assert dialog.selected_index()==1
        captured=[]
        window.run_job=lambda title,function,callback=None:captured.append(function)
        dialog.refresh_directories()
        assert len(captured)==1
        result=captured[0](window.library,type('Progress',(),{'__call__':lambda *args:None,'cancelled':lambda self:False})())
        assert [row['path'] for row in result['offline']]==[configs[1]['path']]
        dialog.remove();assert [entry['kind'] for entry in dialog.folders]==['movie']
        dialog.close()
    finally:window.close()


def test_missing_but_playing_file_is_not_removed(library,tmp_path):
    root=tmp_path/'movies';path=video(root,'Playing.mp4');library.import_folder(root,'movie',fast=True)
    file=library.query()[0]['files'][0];WatchSession(library,file['id']);path.unlink()
    report=scan_directories(library,[{'path':str(root),'kind':'movie'}])
    assert remove_missing(library,report['missing'])=={'removed':0,'skipped':1}
    assert library.db.execute('SELECT 1 FROM files WHERE id=?',(file['id'],)).fetchone()
