import json
import os
from pathlib import Path
import pytest
from lumen.core import Library
from lumen.ingestion import codes, choose, NeedsConfirmation, enqueue, process_pending, confirm
from lumen.media_tools import watch_folders
from lumen.plugins import Plugins
from test_gallery_downloads import manager_for


def imported(library, tmp_path, kind='vr'):
    root=tmp_path/'incoming';root.mkdir()
    video=root/'ABC-123-CD1.mp4';video.write_bytes(b'video-content')
    library.import_folder(root,kind,fast=True)
    return video,library.query()[0]


@pytest.mark.parametrize('name,expected', [('abc_123-CD1.mp4',{'ABC-123'}),('FC2-PPV-1234567',{'FC2-PPV-1234567'}),('FC2_1234567',{'FC2-PPV-1234567'}),('1080p H265',set())])
def test_normalize_number(name,expected):
    assert codes(name)==expected


def test_number_matching_rejects_conflicts_and_wrong_kind(library,tmp_path):
    video,work=imported(library,tmp_path)
    candidate={'id':'123','title':'ABC-123 Title','kind':'movie'}
    assert choose(work,[candidate])==candidate
    for candidates in [[dict(candidate,title='ABC-124')],[candidate,dict(candidate,id='456')],[dict(candidate,kind='series')]]:
        with pytest.raises(NeedsConfirmation):choose(work,candidates)


def test_failure_never_moves_and_confirmation_resumes_after_reopen(library,tmp_path,monkeypatch):
    video,work=imported(library,tmp_path);manager_for(library)
    target=tmp_path/'organized'
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:[])
    enqueue(library,work,'catalog-json',str(target))
    assert process_pending(library)['pending']==1
    assert video.is_file() and not target.exists()
    # Manual matching confirms this identity, then the persistent task resumes.
    confirm(library,work['id'])
    reopened=Library(library.directory)
    try:
        assert process_pending(reopened)['completed']==1
        path=Path(reopened.work(work['id'])['files'][0]['path'])
        assert path.is_relative_to(target) and path.read_bytes()==b'video-content'
        assert not video.exists()
        assert process_pending(reopened)['completed']==0
    finally:reopened.close()


def test_network_retry_fetches_detail_preserves_vr(library,tmp_path,monkeypatch):
    video,work=imported(library,tmp_path);manager_for(library)
    calls=[]
    def run(self,plugin,operation,**kw):
        calls.append((operation,kw))
        if len(calls)==1:raise OSError('network unavailable')
        value={'id':'ABC-123','title':'ABC-123 Full title','kind':'movie','url':'http://localhost/detail'}
        if operation=='detail':value['overview']='Complete overview'
        return [value]
    monkeypatch.setattr(Plugins,'run',run)
    enqueue(library,work,'catalog-json','')
    assert process_pending(library,clock=lambda:100)['retry']==1
    assert not process_pending(library,clock=lambda:120)['completed']
    assert process_pending(library,clock=lambda:200)['completed']==1
    updated=library.work(work['id'])
    assert updated['kind']=='vr' and updated['metadata']['overview']=='Complete overview'
    assert calls[1]==('search',{'query':'ABC-123'})
    assert calls[2][0]=='detail'


def test_watcher_queues_only_stable_files_with_directory_rule(library,tmp_path,monkeypatch):
    root=tmp_path/'watch';root.mkdir();video=root/'ABC-123.mp4';video.write_bytes(b'data');os.utime(video,(1,1))
    library.set_setting('partition:vr',{'plugin':'default','destination':'unused'})
    library.set_setting('watched_folders',[{'path':str(root),'kind':'vr','plugin':'custom','destination':'','settle_seconds':10}])
    watch_folders(library,clock=lambda:100)
    assert not library.db.execute("SELECT 1 FROM tasks WHERE kind='ingest'").fetchone()
    watch_folders(library,clock=lambda:120)
    row=library.db.execute("SELECT payload FROM tasks WHERE kind='ingest'").fetchone()
    payload=json.loads(row['payload']);assert payload['plugin']=='custom' and payload['destination']==''
    watch_folders(library,clock=lambda:140)
    assert library.db.execute("SELECT COUNT(*) FROM tasks WHERE kind='ingest'").fetchone()[0]==1


def test_new_part_after_completed_move_gets_new_journal(library,tmp_path):
    video,work=imported(library,tmp_path);target=tmp_path/'out'
    enqueue(library,work,'',str(target));process_pending(library)
    first=json.loads(library.db.execute("SELECT payload FROM tasks WHERE kind='ingest'").fetchone()[0])
    # A new imported file must not reuse the completed movement journal.
    second=target/work['title']/'ABC-123-CD2.mp4';second.write_bytes(b'second')
    library.import_folder(target,'vr',fast=True)
    updated=library.work(work['id'])
    enqueue(library,updated,'',str(target),force=True)
    next_payload=json.loads(library.db.execute("SELECT payload FROM tasks WHERE kind='ingest'").fetchone()[0])
    assert first['move_id']!=next_payload['move_id']
    assert process_pending(library)['completed']==1


def test_pending_filter_finds_exceptions_outside_first_history_page(library):
    from lumen.tasks import snapshot
    library.task('waiting','ingest','pending',{'work_id':1},error='ambiguous')
    for index in range(110):library.task('history-'+str(index),'background','done',{})
    assert not any(row['id']=='waiting' for row in snapshot(library.directory))
    assert [row['id'] for row in snapshot(library.directory,pending_only=True)]==['waiting']


def test_regular_titles_and_series_do_not_become_video_codes():
    from lumen.ingestion import work_codes
    assert codes('Blade Runner 2049') == set()
    assert work_codes({'kind':'series','title':'Show 123','files':[]}) == set()
