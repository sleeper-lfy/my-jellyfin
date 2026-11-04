import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

import pytest
from PySide6.QtCore import Qt,QMimeData,QUrl,QPoint,QPointF
from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from lumen.ui import MainWindow
from lumen.plugins import Plugins
from lumen.core import ImportCancelled
from lumen.ingestion import enqueue
from test_core import add_work
from test_gallery_downloads import manager_for
from test_pc_stability import spin,until


@pytest.fixture
def window(qapp,tmp_path):
    value=MainWindow(tmp_path/'reported');value.show();spin(qapp)
    for timer in (value.scheduler,value.media_scheduler,value.watch_scheduler,value.resource_scheduler):timer.stop()
    yield value
    value.stop_jobs();value.close()
    until(qapp,lambda:not value.jobs and value._browse_job is None and not value._auxiliary_jobs)
    spin(qapp,.15)


def test_movie_folder_search_keeps_category_and_folder(qapp,window,tmp_path):
    a=add_work(window.library,'Wanted movie');add_work(window.library,'Wanted series',kind='series')
    window.navigate('movie');folder=window.library.work(a)['files'][0]['root']
    window.filters={'folder':folder};window.search.setText('Wanted');window.search.returnPressed.emit();spin(qapp)
    assert window.section=='movie' and window.filters['folder']==folder
    assert [work['id'] for work in window.current_items]==[a]
    window.search.clear();window.search.returnPressed.emit();assert window.section=='movie'


def test_manual_batch_scrapes_more_than_ten_only_requested_works(qapp,window,monkeypatch):
    manager_for(window.library)
    outside=add_work(window.library,'Outside');enqueue(window.library,window.library.work(outside),'catalog-json','')
    ids=[add_work(window.library,'Film alphabet '+chr(65+i)) for i in range(14)]
    queried=[]
    def run(self,plugin,operation,query=None,url=None,**kwargs):
        if operation=='search':
            queried.append(query);identifier=next(i for i in ids if self.library.work(i)['title']==query)
        else:identifier=int(url.rsplit('/',1)[1])
        work=self.library.work(identifier)
        return [{'id':str(identifier),'title':work['title'],'year':work['year'],'kind':'movie','url':f'http://localhost/{identifier}'}]
    monkeypatch.setattr(Plugins,'run',run)
    def inline(title,function,callback=None):
        result=function(window.library,lambda *args:None)
        if callback:callback(result)
    monkeypatch.setattr(window,'run_job',inline)
    window.auto_scrape_import('/unused','movie','catalog-json','',work_ids=ids)
    assert len(queried)==14 and set(queried)=={window.library.work(i)['title'] for i in ids}
    assert all(window.library.work(i)['sources'] for i in ids)
    assert not window.library.work(outside)['sources']
    assert window.library.db.execute('SELECT status FROM tasks WHERE id=?',('ingest-'+str(outside),)).fetchone()[0]=='queued'


def test_import_reports_only_work_ids_touched_by_this_folder(library,tmp_path):
    outside=add_work(library,'Other')
    folder=tmp_path/'new';folder.mkdir();(folder/'New.2024.mp4').write_bytes(b'new-video')
    result=library.import_folder(folder,'movie',fast=True,include_work_ids=True)
    assert len(result['work_ids'])==1 and outside not in result['work_ids']
    assert library.import_folder(folder,'movie',fast=True,include_work_ids=True)['work_ids']==result['work_ids']


def test_close_hides_immediately_and_unblocks_paused_worker(qapp,window):
    entered=threading.Event()
    def work(lib,progress):
        entered.set()
        while not progress.cancelled():time.sleep(.01)
        return {'cancelled':True}
    window.run_job('running',work);until(qapp,entered.is_set)
    window.pause_jobs(True);window.task_budget.set_playback(True)
    window.close();assert not window.isVisible()
    until(qapp,lambda:not window.jobs and window.task_budget.active==0)


def test_drop_still_works_during_job_and_async_browse_and_preserves_batch(qapp,window,tmp_path):
    gate=threading.Event();entered=threading.Event()
    def work(lib,p):entered.set();gate.wait(3);return {}
    window.run_job('busy',work);until(qapp,entered.is_set);window.navigate('movie')
    folders=[tmp_path/f'folder-{i}' for i in range(3)]
    for folder in folders:folder.mkdir()
    try:
        assert window.cards.isEnabled() and window.home_page.isEnabled()
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(folders[0]))])
        target=window.cards.viewport()
        enter=QDragEnterEvent(QPoint(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target,enter);assert enter.isAccepted()
        move=QDragMoveEvent(QPoint(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target,move);assert move.isAccepted()
        drop=QDropEvent(QPointF(20,20),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target,drop);assert drop.isAccepted()
        form=window.import_form;assert form.isVisible() and Path(form.path.text())==folders[0]
        window.import_path(folders[1],pending=[str(folders[2])])
        assert Path(form.path.text())==folders[0] and form.pending==list(map(str,folders[1:]))
        form.submit();assert len(window.job_queue)==3
    finally:gate.set()
    until(qapp,lambda:not window.jobs and not window.job_queue)


@pytest.mark.parametrize('width',[1024,1400])
def test_home_media_cards_wrap_at_readable_size(qapp,window,width):
    window.resize(width,850);window.navigate('home');spin(qapp)
    shortcuts=window.home_page.shortcuts;tiles=list(window.home_page.tiles.values())
    assert all(tile.width()>=230 and tile.height()>=125 for tile in tiles)
    assert len({tile.y() for tile in tiles})>=2
    assert shortcuts.horizontalScrollBar().maximum()==0
    assert all(tile.geometry().right()<=shortcuts.viewport().width() for tile in tiles)


def test_visible_episode_and_season_actions_are_scoped_and_keep_files(qapp,window,monkeypatch):
    series=add_work(window.library,'Show',kind='series')
    with window.library.db:
        window.library.db.execute('UPDATE files SET season=1,episode=1 WHERE work_id=?',(series,))
        for season,episode in [(1,2),(2,1),(0,1)]:
            window.library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES(?,?,?,?,?,?,?)',
                (series,f'/video/season{season}-episode{episode}.mp4',f'ep-{season}-{episode}','/video',100,season,episode))
    window.open_details(series,fetch=False);detail=window.detail_page;requested=[]
    monkeypatch.setattr(detail,'remove_episode_records',lambda ids:requested.append(set(ids)))
    first=detail.files.item(0);detail.files.setCurrentItem(first)
    detail.remove_episodes_action.click();assert requested[-1]=={first.data(Qt.ItemDataRole.UserRole)['id']}
    detail.season_filter.setCurrentIndex(detail.season_filter.findData(1));detail.remove_season_action.click()
    assert requested[-1]=={f['id'] for f in detail.work['files'] if f['season']==1}
    detail.season_filter.setCurrentIndex(detail.season_filter.findData(0));detail.remove_season_action.click()
    assert requested[-1]=={f['id'] for f in detail.work['files'] if f['season']==0}


def test_httpx_plugin_request_can_cancel_while_waiting_for_headers(library,monkeypatch):
    entered=threading.Event();release=threading.Event();cancel=threading.Event()
    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):entered.set();release.wait(4)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Slow);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    manager=Plugins(library);manager.cancelled=cancel.is_set;monkeypatch.setattr(manager,'_curl_binary',lambda:None)
    try:
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(manager.fetch,{'domains':['127.0.0.1'],'config':{'proxy':''}},f'http://127.0.0.1:{server.server_port}/slow')
            assert entered.wait(2);cancel.set()
            with pytest.raises(ImportCancelled):future.result(2)
    finally:release.set();server.shutdown();server.server_close();thread.join(2)


def test_cancelled_move_preserves_source_and_can_resume(library,tmp_path):
    from lumen.files import plan_move,execute_move
    work=add_work(library,'Move cancellation');source=tmp_path/'input.mp4';source.write_bytes(b'media'*2_000_000)
    with library.db:library.db.execute('UPDATE files SET path=?,root=? WHERE work_id=?',(str(source),str(tmp_path),work))
    target=tmp_path/'organized';plan=plan_move(library,work,target)
    def cancel():return any(path.stat().st_size>0 for path in target.rglob('*.partial'))
    with pytest.raises(ImportCancelled):execute_move(library,plan,task_id='cancel-move',cancelled=cancel)
    assert source.is_file() and library.work(work)['files'][0]['path']==str(source)
    assert library.db.execute("SELECT status FROM tasks WHERE id='cancel-move'").fetchone()[0]=='cancelled'
    execute_move(library,task_id='cancel-move')
    assert not source.exists() and Path(library.work(work)['files'][0]['path']).read_bytes()==b'media'*2_000_000


def test_plugin_image_cancellation_is_not_swallowed_as_image_failure(library,monkeypatch):
    manager=manager_for(library);identifier=add_work(library,'Cancel images')
    def cancelled(*args,**kwargs):raise ImportCancelled('stop')
    monkeypatch.setattr(manager,'fetch',cancelled)
    with pytest.raises(ImportCancelled):manager.merge('catalog-json',{'id':'cancel-image','title':'Cancel images','kind':'movie','year':2024,'url':'http://localhost/movie','poster':'http://localhost/poster.jpg'},identifier)
    assert not library.db.execute("SELECT 1 FROM tasks WHERE kind='image' AND status='failed'").fetchone()


def test_episode_file_deletion_preserves_other_season_and_shared_sidecars(library,tmp_path):
    from lumen.files import plan_delete,execute_delete
    work=add_work(library,'Selective delete',kind='series')
    selected=tmp_path/'episode.mp4';selected.write_bytes(b'episode')
    other=tmp_path/'episode.en.mp4';other.write_bytes(b'other episode')
    shared=tmp_path/'episode.en.srt';shared.write_text('shared subtitle')
    own=tmp_path/'episode.nfo';own.write_text('<episodedetails/>')
    with library.db:
        library.db.execute('UPDATE files SET path=?,root=? WHERE work_id=?',(str(selected),str(tmp_path),work))
        library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES(?,?,?,?,?,?,?)',(work,str(other),'other',str(tmp_path),100,2,1))
    chosen=[file['id'] for file in library.work(work)['files'] if file['path']==str(selected)]
    assert plan_delete(library,work,file_ids=chosen)['paths']==[str(selected)]
    result=execute_delete(library,work,file_ids=chosen)
    assert result['removed']==1 and not result['removed_work']
    assert not selected.exists() and not own.exists()
    assert other.exists() and shared.exists() and len(library.work(work)['files'])==1
    with pytest.raises(ValueError):execute_delete(library,work,file_ids=chosen)


def test_delete_episode_files_routes_only_chosen_ids(qapp,window,monkeypatch):
    work=add_work(window.library,'Chosen episode',kind='series');window.open_details(work,fetch=False)
    seen=[];monkeypatch.setattr(window,'delete_work_files',lambda work_id,ids:seen.append((work_id,ids)))
    detail=window.detail_page;detail.delete_selected_episode_files(False)
    assert seen==[(work,[detail.work['files'][0]['id']])]


def test_actual_application_exits_after_closing_during_a_job(tmp_path):
    import os,subprocess,sys
    script='''
import sys,time
from pathlib import Path
from PySide6.QtCore import QTimer
import lumen.ui as ui
Original=ui.MainWindow
class Busy(Original):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        def task(lib,progress):
            (lib.directory/'started').write_text('started')
            while not progress.cancelled():time.sleep(.01)
            (lib.directory/'cancelled').write_text('cancelled')
            return {'cancelled':True}
        self.run_job('close regression',task)
        def close_when_started():
            if not (self.library.directory/'started').exists():QTimer.singleShot(20,close_when_started);return
            self.close()
        QTimer.singleShot(20,close_when_started)
ui.MainWindow=Busy
from lumen.app import main
sys.argv=['lumen','--data-dir',sys.argv[1]]
raise SystemExit(main())
'''
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
    env['PYTHONPATH']=str(Path(__file__).parents[1]/'src')+os.pathsep+env.get('PYTHONPATH','')
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path/'actual-close')],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr[-3000:]
    assert (tmp_path/'actual-close'/'cancelled').exists()


def test_remove_episode_confirmation_and_callback_keep_other_episodes(qapp,window,monkeypatch):
    work=add_work(window.library,'Episode callback',kind='series')
    with window.library.db:
        window.library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES(?,?,?,?,?,?,?)',(work,'/video/other.mp4','keep','/video',100,2,1))
    window.open_details(work,fetch=False);detail=window.detail_page
    chosen=detail.work['files'][0];prompts=[];reloaded=[]
    def confirm(prompt):prompts.append((prompt.text(),prompt.detailedText()));return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox,'exec',confirm)
    monkeypatch.setattr(window,'reload_details',reloaded.append)
    def inline(title,function,callback):
        result=function(window.library,lambda *args:None);callback(result)
    monkeypatch.setattr(window,'run_job',inline)
    detail.remove_episode_records([chosen['id']])
    assert len(window.library.work(work)['files'])==1 and reloaded==[work]
    assert '视频文件保留' in prompts[0][0] and Path(chosen['path']).name in prompts[0][1]


def test_reopening_import_preserves_visible_draft_but_clears_cancelled_batch(window,tmp_path):
    first=tmp_path/'first';second=tmp_path/'second'
    window.import_path(first,pending=[str(second)]);form=window.import_form
    window.import_dialog();assert form.pending==[str(second)]
    form.reject();window.import_dialog();assert form.pending==[]
    form.reject()
