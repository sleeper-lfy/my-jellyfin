import json
from pathlib import Path
import pytest
from lumen import core,nfo
from lumen.core import WatchSession
from lumen.media_tools import add_bookmark
from test_series_folders import files


@pytest.mark.parametrize('fast',[False,True])
def test_total_directory_groups_creators_and_nested_clips_without_nfo_or_episode_numbers(library,tmp_path,monkeypatch,fast):
    monkeypatch.setattr(core,'probe',lambda path:30)
    monkeypatch.setattr(core,'thumbnail',lambda *args:None)
    monkeypatch.setattr(nfo,'load',lambda *args:pytest.fail('Fans never reads movie/series NFO'))
    root=tmp_path/'Fans'
    alice=files(root/'Alice',['片段10.mp4','片段2.mp4'])
    alice+=files(root/'Alice'/'2025'/'Travel',['未编号的日常.mkv'])
    bob=files(root/'Bob',['Live stream.mp4'])
    loose=files(root,['Loose clip.mp4'])
    result=library.import_folder(root,'fans',fast=fast)
    assert result['imported']==5 and not result['errors'],result
    works=library.query({'kinds':['fans']});assert len(works)==3
    by_name={work['title']:work for work in works}
    assert set(by_name)=={'Alice','Bob','Fans'}
    assert {Path(file['path']) for file in by_name['Alice']['files']}==set(alice)
    assert {Path(file['path']) for file in by_name['Bob']['files']}==set(bob)
    assert {Path(file['path']) for file in by_name['Fans']['files']}==set(loose)
    assert all(file['season'] is None and file['episode'] is None for work in works for file in work['files'])
    assert by_name['Alice']['metadata']['creator']=='Alice'
    assert by_name['Alice']['metadata']['fans_roots']==[str(root/'Alice')]
    ordered=[Path(file['path']).name for file in by_name['Alice']['files']]
    assert ordered.index('片段2.mp4')<ordered.index('片段10.mp4')
    before={file['path']:(file['id'],file['work_id']) for work in works for file in work['files']}
    again=library.import_folder(root,'fans',fast=fast)
    assert again['duplicates']==5 and not again['errors'],again
    after={file['path']:(file['id'],file['work_id']) for work in library.query({'kinds':['fans']}) for file in work['files']}
    assert after==before and all(path.exists() for path in [*alice,*bob,*loose])


def test_same_display_name_never_auto_merges_and_partial_retry_keeps_existing_creator(library,tmp_path):
    first=files(tmp_path/'First'/'Same creator',['01.mp4','02.mp4'])
    second=files(tmp_path/'Second'/'Same creator',['03.mp4'])
    assert library.import_folder(tmp_path/'First','fans',fast=True,candidates=first[:1])['imported']==1
    work=library.query({'kinds':['fans']})[0]
    library.merge_fans_folders([work['id']],work['id'],creator='Custom author')
    result=library.import_folder(tmp_path/'First','fans',fast=True,candidates=first[1:])
    assert result['imported']==1 and not result['errors']
    assert library.work(work['id'])['title']=='Custom author' and len(library.work(work['id'])['files'])==2
    library.import_folder(tmp_path/'Second','fans',fast=True)
    assert len(library.query({'kinds':['fans']}))==2
    assert set(file['id'] for file in library.work(work['id'])['files'])=={1,2}


@pytest.mark.parametrize('fast',[False,True])
def test_identical_bytes_in_other_authors_and_movies_do_not_hide_fans_paths(library,tmp_path,monkeypatch,fast):
    monkeypatch.setattr(core,'probe',lambda path:30);monkeypatch.setattr(core,'thumbnail',lambda *args:None)
    movie_root=tmp_path/'Movies';movie=files(movie_root,['Existing.mp4'])[0];movie.write_bytes(b'identical archive clip')
    library.import_folder(movie_root,'movie',fast=fast)
    root=tmp_path/'Fans';one=files(root/'Alice',['same.mp4'])[0];two=files(root/'Bob',['same.mp4'])[0]
    one.write_bytes(movie.read_bytes());two.write_bytes(movie.read_bytes())
    result=library.import_folder(root,'fans',fast=fast)
    assert result['imported']==2 and result['duplicates']==0 and not result['errors'],result
    works=library.query({'kinds':['fans']});assert len(works)==2 and all(len(work['files'])==1 for work in works)
    assert len(library.query({'kinds':['movie']}))==1
    old={work['title']:work['id'] for work in works}
    again=library.import_folder(root,'fans',fast=fast)
    assert again['duplicates']==2 and again['imported']==0 and not again['errors']
    assert {work['title']:work['id'] for work in library.query({'kinds':['fans']})}==old


def test_other_videos_are_reclassified_without_losing_personal_state_progress_history_bookmarks_or_queue(library,tmp_path):
    root=tmp_path/'Fans';original=files(root/'Author',['First.mp4','Second.mp4'])
    library.import_folder(root,'other',fast=True)
    works=library.query({'kinds':['other']});ids=[work['files'][0]['id'] for work in works]
    source_ids=[work['id'] for work in works]
    library.update_personal(source_ids[0],favorite=True,watchlist=True)
    with library.db:
        library.db.execute('UPDATE files SET position=24,duration=300 WHERE id=?',(ids[0],))
    clock=[0.0];session=WatchSession(library,ids[0],lambda:clock[0]);session.tick(0,True)
    clock[0]=1;session.tick(1,True);session.finish()
    bookmark=add_bookmark(library,ids[0],12,'Keep this scene')
    library.edit_queue(source_ids)
    before_stats=library.stats()['seconds'];before=[path.read_bytes() for path in original]
    result=library.import_folder(root,'fans',fast=True)
    assert result['imported']==result['reclassified']==2 and not result['errors'],result
    assert not library.query({'kinds':['other']})
    work=library.query({'kinds':['fans']})[0]
    assert {file['id'] for file in work['files']}==set(ids)
    assert work['favorite']==work['watchlist']==1
    assert library.work(work['id'])['files'][0]['season'] is None
    assert library.db.execute('SELECT position FROM files WHERE id=?',(ids[0],)).fetchone()[0]==1
    assert library.db.execute('SELECT file_id FROM bookmarks WHERE id=?',(bookmark['id'],)).fetchone()[0]==ids[0]
    assert library.db.execute('SELECT file_id FROM sessions WHERE id=?',(session.id,)).fetchone()[0]==ids[0]
    assert library.stats()['seconds']==before_stats
    assert library.setting('queue')['ids']==[work['id']]
    assert [path.read_bytes() for path in original]==before


def test_older_other_record_without_fast_cache_keeps_duration_when_adopted(library,tmp_path,monkeypatch):
    monkeypatch.setattr(core,'probe',lambda path:123);monkeypatch.setattr(core,'thumbnail',lambda *args:None)
    root=tmp_path/'Fans';files(root/'Creator',['One.mp4'])
    library.import_folder(root,'other')
    old=library.query({'kinds':['other']})[0]['files'][0]
    assert not library.db.execute('SELECT 1 FROM import_cache WHERE file_id=?',(old['id'],)).fetchone()
    result=library.import_folder(root,'fans',fast=True)
    new=library.query({'kinds':['fans']})[0]['files'][0]
    assert not result['errors'] and new['id']==old['id'] and new['duration']==123


def test_manual_merge_keeps_all_directory_bindings_and_history_then_rescan_joins_target(library,tmp_path,monkeypatch):
    root=tmp_path/'Fans'
    one=files(root/'Alice old',['First.mp4'])
    two=files(root/'Alice new'/'Archive',['Second.mp4'])
    library.import_folder(root,'fans',fast=True)
    target,source=library.query({'kinds':['fans']})
    library.update_personal(target['id'],rating=9)
    library.update_personal(source['id'],favorite=True,watchlist=True)
    file_id=source['files'][0]['id']
    with library.db:library.db.execute('UPDATE files SET position=14 WHERE id=?',(file_id,))
    bookmark=add_bookmark(library,file_id,8,'Keep after merge')
    library.edit_queue([source['id'],target['id']])
    with library.db:library.db.execute("DELETE FROM name_keys WHERE key LIKE 'fans-folder:%'")
    with monkeypatch.context() as local:
        local.setattr(Path,'resolve',lambda *args,**kwargs:pytest.fail('Logical merge must not inspect source directories'))
        local.setattr(Path,'stat',lambda *args,**kwargs:pytest.fail('Logical merge must not inspect source directories'))
        result=library.merge_fans_folders([source['id']],target['id'],creator='Alice')
    assert {key:result[key] for key in ('work_id','merged','files','creator')}=={'work_id':target['id'],'merged':1,'files':2,'creator':'Alice'}
    assert set(result['roots'])=={str(root/'Alice old'),str(root/'Alice new')}
    work=library.work(target['id'])
    assert work['rating']==9 and work['favorite']==work['watchlist']==1
    assert work['title']==work['metadata']['creator']=='Alice'
    assert tuple(library.db.execute('SELECT position,work_id FROM files WHERE id=?',(file_id,)).fetchone())==(14,target['id'])
    assert library.db.execute('SELECT file_id FROM bookmarks WHERE id=?',(bookmark['id'],)).fetchone()[0]==file_id
    assert library.setting('queue')['ids']==[target['id']]
    extra=files(root/'Alice old'/'New directory',['Third.mp4'])
    scanned=library.import_folder(root,'fans',fast=True,candidates=extra)
    assert scanned['imported']==1 and scanned['duplicates']==0 and not scanned['errors'],scanned
    assert len(library.query({'kinds':['fans']}))==1
    assert {Path(file['path']) for file in library.work(target['id'])['files']}==set([*one,*two,*extra])


def test_invalid_merge_is_atomic_and_movie_paths_are_never_silently_reclassified(library,tmp_path):
    from test_core import add_work
    root=tmp_path/'Fans';videos=files(root/'Author',['Local.mp4'])
    library.import_folder(root,'movie',fast=True);movie=library.query({'kinds':['movie']})[0]
    result=library.import_folder(root,'fans',fast=True)
    assert len(result['errors'])==1 and not library.query({'kinds':['fans']})
    assert library.work(movie['id'])['files'][0]['id']==1 and videos[0].exists()
    first=add_work(library,'Creator A','fans');second=add_work(library,'Creator B','fans')
    before=library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0]
    with pytest.raises(ValueError,match='Fans'):library.merge_fans_folders([second,movie['id']],first)
    assert library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0]==before
    assert library.work(second)['files']
    with pytest.raises(ValueError):library.merge_fans_folders([second],first,creator=' ')
    assert library.work(second)['files']


def test_manual_merge_failure_rolls_back_previous_merges_and_queue(library,tmp_path,monkeypatch):
    root=tmp_path/'Fans'
    for name in ('First','Second','Third'):files(root/name,['Clip.mp4'])
    library.import_folder(root,'fans',fast=True)
    works=library.query({'kinds':['fans']});ids=[work['id'] for work in works]
    owners={file['id']:file['work_id'] for work in works for file in work['files']}
    queue=library.edit_queue(ids);original=library.merge_works;calls=[]
    def interrupted(source,target,commit=True):
        result=original(source,target,commit=commit);calls.append(source)
        if len(calls)==2:raise OSError('Injected write failure')
        return result
    monkeypatch.setattr(library,'merge_works',interrupted)
    with pytest.raises(OSError,match='write failure'):library.merge_fans_folders(ids[1:],ids[0],creator='Combined')
    assert {work['id'] for work in library.query({'kinds':['fans']})}==set(ids)
    assert {file['id']:file['work_id'] for work in library.query({'kinds':['fans']}) for file in work['files']}==owners
    assert library.setting('queue')==queue


def test_cancelled_scan_retains_completed_creators_and_resume_does_not_duplicate(library,tmp_path):
    root=tmp_path/'Fans';files(root/'Creator',['First.mp4','Second.mp4'])
    stopped=[False]
    def progress(done,total,message):
        if done==1 and message.startswith('已处理'):stopped[0]=True
    result=library.import_folder(root,'fans',progress,fast=True,cancelled=lambda:stopped[0])
    assert result['cancelled'] and result['imported']==1 and not result['errors']
    file_id=library.query({'kinds':['fans']})[0]['files'][0]['id']
    again=library.import_folder(root,'fans',fast=True)
    assert again['imported']==again['duplicates']==1 and not again['errors']
    work=library.query({'kinds':['fans']})[0]
    assert len(work['files'])==2 and file_id in {file['id'] for file in work['files']}


def test_fans_never_enters_or_influences_movie_recommendations(library):
    from test_core import add_work
    fan=add_work(library,'Creator','fans',metadata={'tags':['favoured'],'actors':[{'name':'Actor','gender':'female'}]})
    movie=add_work(library,'Movie',metadata={'tags':['favoured'],'actors':[{'name':'Actor','gender':'female'}]})
    library.update_personal(fan,favorite=True,rating=10)
    assert [work['id'] for work in library.recommendations()]==[movie]
    assert library.recommendations()[0]['score']==0
