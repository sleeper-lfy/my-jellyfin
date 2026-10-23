import json
import os
import shutil
from pathlib import Path
import time
import httpx
import pytest
from lumen.core import Library
from lumen.media_tools import preferences,add_bookmark,bookmarks,capture_bookmark,delete_bookmark,watch_folders,audit_library
from lumen.server import LanServer


def test_preferences_merge_and_reject_invalid_values(library,video_factory):
    library.import_folder(video_factory('Preferences.mp4').parent,'vr',fast=True)
    file=library.query()[0]['files'][0]
    preferences(library,file['id'],{'subtitle_delay':1.2,'vr':{'fish':True,'fov':75,'yaw':12}})
    preferences(library,file['id'],{'subtitle_size':28,'vr':{'headset':True}})
    saved=preferences(library,file['id'])
    assert saved['vr']=={'fish':True,'fov':75,'yaw':12,'headset':True}
    assert saved['subtitle_delay']==1.2 and saved['subtitle_size']==28
    saved=preferences(library,file['id'],{'vr':{'tracking_sensitivity':.5,'tracking_smoothing':60,'tracking_invert_pitch':True}})
    assert saved['vr']['tracking_sensitivity']==.5 and saved['vr']['fish'] is True
    for changes in ({'subtitle_delay':float('nan')},{'subtitle_size':True},{'vr':{'fov':0}},{'vr':{'fish':'yes'}},{'vr':{'pitch':100}},{'script':'bad'},{'vr':{'tracking_sensitivity':0}},{'vr':{'tracking_smoothing':200}},{'vr':{'tracking_invert_pitch':1}}):
        with pytest.raises(ValueError):preferences(library,file['id'],changes)
    reopened=Library(library.directory,initialize=False)
    assert preferences(reopened,file['id'])==saved;reopened.close()


def test_bookmark_preserves_watch_progress_and_captures_actual_frame(library,video_factory):
    source=video_factory('Bookmark.mp4','blue',4)
    library.import_folder(source.parent,'movie');work=library.query()[0];file=work['files'][0]
    mark=add_bookmark(library,file['id'],1.5,'Scene','A note')
    image=Path(capture_bookmark(library,mark['id']))
    assert image.is_relative_to(library.directory/'cache') and image.read_bytes().startswith(b'\xff\xd8')
    assert bookmarks(library,file['id'])[0]['position']==1.5
    assert library.work(work['id'])['files'][0]['position']==file['position']
    assert library.stats()['seconds']==0
    for bad in (-1,999,float('inf'),True):
        with pytest.raises(ValueError):add_bookmark(library,file['id'],bad)
    delete_bookmark(library,mark['id']);assert bookmarks(library,file['id'])==[] and source.is_file()


def test_monitor_waits_for_stability_and_imports_nfo_changes_without_touching_personal_data(library,video_factory,tmp_path):
    root=tmp_path/'watched';root.mkdir();video=root/'Watched.mp4';shutil.copyfile(video_factory('Watcher.mp4'),video)
    os.utime(video,(100,100));clock=[1000.0]
    library.set_setting('watched_folders',[{'path':str(root),'kind':'movie','settle_seconds':10}])
    assert watch_folders(library,clock=lambda:clock[0])['waiting']==1
    clock[0]+=5
    with video.open('ab') as stream:stream.write(b'padding')
    os.utime(video,(100,100))
    assert watch_folders(library,clock=lambda:clock[0])['imported']==0
    clock[0]+=11;assert watch_folders(library,clock=lambda:clock[0])['imported']==1
    work=library.query()[0];library.update_personal(work['id'],favorite=True,rating=9)
    video.with_suffix('.nfo').write_text('<movie><title>Updated title</title><plot>New plot</plot></movie>',encoding='utf-8')
    assert watch_folders(library,clock=lambda:clock[0])['updated']==0
    clock[0]+=11;assert watch_folders(library,clock=lambda:clock[0])['updated']==1
    updated=library.work(work['id']);assert updated['title']=='Updated title' and updated['favorite'] and updated['rating']==9
    assert watch_folders(library,clock=lambda:clock[0])['imported']==0
    root.rename(tmp_path/'offline')
    assert watch_folders(library,clock=lambda:clock[0])['offline']==[str(root)]
    assert library.work(work['id'])['files']


def test_audit_distinguishes_missing_files_from_offline_roots_and_never_deletes(library,video_factory,tmp_path):
    root=tmp_path/'drive';root.mkdir();video=root/'Audit.mp4';shutil.copyfile(video_factory('Audit.mp4'),video)
    library.import_folder(root,'movie',fast=True);work=library.query()[0]
    video.with_suffix('.nfo').write_text('<movie>broken',encoding='utf-8')
    report=audit_library(library);assert {'invalid_nfo','missing_cover'}<={row['kind'] for row in report['issues']}
    video.unlink();report=audit_library(library);assert any(row['kind']=='file_missing' for row in report['issues'])
    root.rename(tmp_path/'unmounted');report=audit_library(library)
    assert {row['kind'] for row in report['issues']}=={'directory_offline'}
    assert library.work(work['id'])['files'] and library.setting('last_audit')['checked']==1


def test_authenticated_preferences_bookmarks_and_background_screenshot_api(library,video_factory):
    library.import_folder(video_factory('API bookmark.mp4').parent,'movie')
    work=library.query()[0];file=work['files'][0];server=LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=None);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            route=f"/api/files/{file['id']}"
            assert client.get(route+'/preferences',headers={'Authorization':''}).status_code==401
            assert client.post(route+'/preferences',json={'subtitle_delay':-.3,'vr':{'fish':True,'fov':80}}).status_code==200
            assert client.get(route+'/preferences').json()['vr']['fov']==80
            assert client.post(route+'/preferences',json={'vr':{'fov':500}}).status_code==400
            assert client.post(route+'/bookmarks',json={'position':-1}).status_code==400
            response=client.post(route+'/bookmarks',json={'position':1,'title':'API scene','note':'Saved'})
            assert response.status_code==201;identifier=response.json()['id']
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                marks=client.get(route+'/bookmarks').json()['items']
                if marks[0]['image']:break
                time.sleep(.05)
            assert marks[0]['image'] and client.get(marks[0]['image']).content.startswith(b'\xff\xd8')
            detail=client.get(f"/api/works/{work['id']}").json()
            assert detail['bookmarks'][0]['id']==identifier
            assert str(library.directory) not in json.dumps(detail['bookmarks'])
            assert client.get('/api/remote').status_code==403
            assert client.post('/api/bookmarks/'+identifier+'/delete',json={}).status_code==200
            assert client.get(route+'/bookmarks').json()['items']==[]
    finally:server.stop()


def test_old_backup_is_migrated_in_a_copy(library,video_factory,tmp_path):
    import sqlite3
    from lumen.backup import restore_database
    library.import_folder(video_factory('Old backup.mp4').parent,'movie',fast=True)
    backup=tmp_path/'old.sqlite';library.backup(backup)
    db=sqlite3.connect(backup);db.execute('DROP TABLE bookmarks');db.execute('DROP TABLE playback_preferences');db.commit();db.close()
    original=backup.read_bytes();work=library.query()[0];library.update_personal(work['id'],favorite=True)
    restore_database(library,backup)
    assert not library.work(work['id'])['favorite'] and backup.read_bytes()==original
    assert preferences(library,work['files'][0]['id'])=={}


def test_candidate_import_cannot_import_files_outside_selected_root(library,video_factory,tmp_path):
    root=tmp_path/'empty';root.mkdir();outside=video_factory('Outside.mp4')
    result=library.import_folder(root,'movie',fast=True,candidates=[outside])
    assert result['imported']==0 and library.query()==[]


def test_download_pause_and_cancellation_share_the_global_task_budget(library,monkeypatch):
    import threading
    from lumen import downloads
    from lumen.core import check_cancelled
    from lumen.task_journal import TaskBudget
    ids=[]
    for name in ('one','two'):
        with library.db:
            row=library.db.execute('INSERT INTO works(identity,kind,title,added,metadata) VALUES (?,?,?,?,?)',(name,'movie',name,'2026-10-23',json.dumps({'download_url':[{'url':'https://example.test/'+name,'method':'direct'}]})))
            ids.append(row.lastrowid)
    entered=threading.Event();active=[]
    def running(lib,work_id,index,cancelled=None,task_id=None,**kwargs):
        active.append(work_id);entered.set()
        while True:check_cancelled(cancelled);time.sleep(.01)
    monkeypatch.setattr(downloads,'download_to_library',running)
    budget=TaskBudget(1);queue=downloads.DownloadQueue(library.directory,budget=budget)
    try:
        first=queue.submit(ids[0],0);assert entered.wait(3)
        queue.pause(True);second=queue.submit(ids[1],0);time.sleep(.15)
        assert active==[ids[0]] and budget.active==1
        assert queue.cancel(second) and queue.cancel(first)
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            states=[library.db.execute('SELECT status FROM tasks WHERE id=?',(identifier,)).fetchone()[0] for identifier in (first,second)]
            if states==['cancelled','cancelled']:break
            time.sleep(.03)
        assert states==['cancelled','cancelled'] and active==[ids[0]]
        assert budget.active==0
    finally:queue.pause(False);queue.stop()
