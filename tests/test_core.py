from pathlib import Path
import json
import shutil
import sqlite3
import pytest
from lumen.core import Library, WatchSession, parse_name, identity, now
from lumen.files import plan_move, execute_move, safe_name
from lumen.backup import restore_database


def add_work(library, title, kind='movie', year=2024, metadata=None, local=True):
    with library.db:
        cursor = library.db.execute('INSERT INTO works(identity,kind,title,year,metadata,added) VALUES (?,?,?,?,?,?)',
             (identity(title,year,kind),kind,title,year,json.dumps(metadata or {}),now()))
        work_id = cursor.lastrowid
        if local:
            library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',
                 (work_id,f'/media/{title}.mp4',title,'/media',1000,1,1))
    return work_id


def test_real_import_thumbnail_duplicate_and_restart(library, video_factory, tmp_path):
    source = video_factory()
    result = library.import_folder(source.parent, 'movie')
    assert result == {'imported':1,'duplicates':0,'errors':[],'warnings':[]}
    work = library.query()[0]
    assert work['title'] == 'Sample' and work['year'] == 2024
    assert Path(work['thumbnail']).stat().st_size > 100
    assert work['files'][0]['duration'] > 3
    assert source.exists()
    assert library.import_folder(source.parent,'movie')['duplicates'] == 1
    copy = tmp_path/'copies'
    copy.mkdir()
    shutil.copy2(source,copy/'renamed.mp4')
    assert library.import_folder(copy,'movie')['duplicates'] == 1
    reopened = Library(library.directory)
    assert reopened.query()[0]['files'][0]['path'] == str(source)
    reopened.close()


def test_invalid_video_logged(library, tmp_path):
    root = tmp_path/'invalid'
    root.mkdir()
    (root/'bad.mp4').write_bytes(b'not a video')
    result = library.import_folder(root, 'movie')
    assert len(result['errors']) == 1 and not library.query()
    assert library.db.execute('SELECT status FROM tasks').fetchone()[0] == 'partial'


def test_series_random_unit_resume_and_no_repeat(library):
    a = add_work(library,'Film')
    b = add_work(library,'Show','series')
    with library.db:
        library.db.execute('UPDATE files SET completed=1 WHERE work_id=?',(b,))
        library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode,position) VALUES (?,?,?,?,?,?,?,?)',
                          (b,'/media/show-e2.mp4','e2','/media',1000,1,2,123))
    queue = library.shuffle({})
    assert set(queue['ids']) == {a,b} and len(queue['ids']) == 2
    assert library.resume_file(b)['episode'] == 2
    assert library.resume_file(b)['position'] == 123
    first = library.queue_step()
    assert library.queue_step(1) != first
    assert library.queue_step(1) is None
    assert library.queue_step(1) is None
    reopened = Library(library.directory)
    assert reopened.setting('queue')['index'] == 2
    reopened.close()


def test_all_results_filters_rating_and_smart_lists(library):
    for i in range(125):
        work_id = add_work(library,f'Film{i}',metadata={'tags':['drama','mystery'] if i%2 else ['comedy'], 'aliases':['Alias'+str(i)]})
        if i%2:
            library.update_personal(work_id,rating=8,favorite=True)
    f = {'tags_all':['drama'], 'tags_not':['comedy'], 'year_min':2020, 'rating_min':7, 'favorite':True}
    expected = {w['id'] for w in library.query(f)}
    assert len(expected) == 62
    assert len(library.query(f,limit=10)) == 10
    assert set(library.shuffle(f)['ids']) == expected
    assert len(library.query({'query':'Alias124'})) == 1
    assert library.query({'kinds':[]}) == []
    assert library.query({'folder':'/medi'}) == []
    assert len(library.query({'folder':'/media'})) == 125
    with pytest.raises(ValueError): library.update_personal(1,rating=0)
    with pytest.raises(ValueError): library.update_personal(1,rating=1.5)
    library.update_personal(1,rating=None)
    assert library.work(1)['rating'] is None


def test_actual_watch_time_threshold_pause_seek_speed(library):
    work_id = add_work(library,'Clock')
    file_id = library.work(work_id)['files'][0]['id']
    clock = [0.0]
    session = WatchSession(library,file_id,lambda:clock[0])
    session.tick(0,True)
    for second in range(1,601):
        clock[0] = second
        session.tick(second,True)
    assert library.stats()['seconds'] == 600
    assert library.stats()['valid'] == 0
    clock[0] += 1
    session.tick(601,True)
    assert library.stats()['valid'] == 1
    clock[0] += 100
    session.tick(601,False)
    clock[0] += 1
    session.tick(900,True,seeking=True)
    clock[0] += 1
    session.tick(902,True,rate=2)
    clock[0] += 1
    session.tick(902,True) # buffering
    clock[0] += 1
    session.tick(100,True) # backward seek
    assert library.stats()['seconds'] == 602
    session.finish()
    assert library.stats()['movies'] == 1
    assert sum(library.stats()['days'].values()) == 602


def test_actresses_average_aliases_and_versions(library):
    ids=[]
    for i, score in enumerate([9,8,10,None]):
        actor = {'name':'Alice' if i%2 else '艾丽丝','gender':'female','aliases':['Alice','艾丽丝']}
        work_id = add_work(library,f'Film{i}',metadata={'actors':[actor,{'name':'Unknown'},{'name':'Bob','gender':'male'}]})
        library.update_personal(work_id,rating=score)
        ids.append(work_id)
    with library.db:
        library.db.execute('INSERT INTO files(work_id,path,digest,root,duration) VALUES (?,?,?,?,?)',(ids[0],'/media/alternate.mkv','alternate','/media',1000))
    wall = library.actresses()
    assert len(wall) == 1
    assert wall[0]['average'] == 9 and wall[0]['rated'] == 3 and wall[0]['count'] == 4
    assert library.actresses(minimum=5) == []


def test_recommendation_is_explainable_separate_from_shuffle(library):
    liked = add_work(library,'Liked',metadata={'tags':['mystery']})
    similar = add_work(library,'Similar',metadata={'tags':['mystery']})
    unrelated = add_work(library,'Unrelated',metadata={'tags':['comedy']})
    hidden = add_work(library,'Hidden',metadata={'tags':['mystery']})
    library.update_personal(liked,rating=10)
    library.update_personal(hidden,disliked=True)
    result=library.recommendations()
    # Explicit negative feedback is stronger than one high rating.
    assert hidden not in {w['id'] for w in result}
    library.update_personal(hidden,disliked=False)
    result=library.recommendations()
    assert next(w for w in result if w['id']==similar)['score'] > next(w for w in result if w['id']==unrelated)['score']
    assert 'mystery' in next(w for w in result if w['id']==similar)['reasons'][0]
    assert set(library.shuffle({})['ids']) == {liked,similar,unrelated,hidden}


def test_safe_move_real_video_sidecar_collision_and_retry(library, video_factory, tmp_path):
    root = tmp_path/'source'
    root.mkdir()
    source = root/'Safe.2023.mp4'
    shutil.copy2(video_factory('Safe.2023.mp4', 'green'),source)
    subtitle=root/'Safe.2023.zh.srt'
    subtitle.write_text('1\n00:00:00,000 --> 00:00:01,000\n字幕\n',encoding='utf-8')
    library.import_folder(root,'movie')
    w=library.query()[0]
    plan=plan_move(library,w['id'],tmp_path/'destination')
    assert len(plan)==2
    target=Path(plan[0]['target'])
    target.parent.mkdir(parents=True)
    target.write_text('existing', encoding='utf-8')
    with pytest.raises(FileExistsError): execute_move(library,plan,task_id='move')
    assert source.exists() and target.read_text(encoding='utf-8')=='existing'
    target.unlink() # test owns this simulated colliding file
    execute_move(library,task_id='move')
    assert not source.exists() and not subtitle.exists()
    assert Path(library.work(w['id'])['files'][0]['path']).is_file()
    assert library.db.execute('SELECT status FROM tasks WHERE id="move"').fetchone()[0]=='done'
    execute_move(library,task_id='move') # completed operations are idempotent


def test_move_refuses_changed_source(library,video_factory,tmp_path):
    folder=tmp_path/'input'; folder.mkdir()
    file=folder/'Changed.mp4'; shutil.copy2(video_factory(),file)
    library.import_folder(folder,'movie')
    plan=plan_move(library,library.query()[0]['id'],tmp_path/'out')
    file.write_bytes(file.read_bytes()+b'changed')
    with pytest.raises(ValueError): execute_move(library,plan)
    assert file.exists()


def test_other_structure_and_no_metadata_needed(library,video_factory,tmp_path):
    root=tmp_path/'tutorials'; sub=root/'chapter1'; sub.mkdir(parents=True)
    shutil.copy2(video_factory('Lesson.mp4','red'),sub/'Lesson.mp4')
    library.import_folder(root,'other')
    work=library.query({'kinds':['other']})[0]
    assert work['metadata']=={}
    plan=plan_move(library,work['id'],tmp_path/'archive')
    assert Path(plan[0]['target']).relative_to(tmp_path/'archive')==Path('tutorials/chapter1/Lesson.mp4')
    assert work['thumbnail']


def test_backup_restore_checks_schema_and_preserves_current(library,tmp_path):
    original=add_work(library,'Original')
    backup=tmp_path/'backup.sqlite'
    library.backup(backup)
    library.update_personal(original,rating=10)
    restore_database(library,backup)
    assert library.work(original)['rating'] is None
    assert list(library.directory.glob('before-restore-*.sqlite'))
    with pytest.raises(FileExistsError): library.backup(backup)
    invalid=tmp_path/'bad.sqlite'
    sqlite3.connect(invalid).close()
    with pytest.raises(ValueError): restore_database(library,invalid)


@pytest.mark.parametrize('name,season,episode',[('Show.S02E03.mkv',2,3),('Show.1x04.mp4',1,4)])
def test_episode_parse(name,season,episode):
    parsed=parse_name(name,'series')
    assert parsed['title']=='Show' and parsed['season']==season and parsed['episode']==episode


def test_windows_reserved_names():
    assert safe_name('CON')=='_CON'
    assert safe_name('A:B?')=='A_B_'


def test_recovery_after_publication_before_source_delete(library,video_factory,tmp_path):
    from lumen.core import fingerprint
    folder=tmp_path/'source2';folder.mkdir()
    source=folder/'Crash.mp4';shutil.copy2(video_factory(),source)
    library.import_folder(folder,'movie')
    w=library.query()[0]
    plan=plan_move(library,w['id'],tmp_path/'target2')
    target=Path(plan[0]['target']);target.parent.mkdir(parents=True)
    shutil.copy2(source,target)
    plan[0]['state']='published'
    library.task('crash','move','running',plan)
    execute_move(library,task_id='crash')
    assert not source.exists() and fingerprint(target)==plan[0]['digest']
    assert library.work(w['id'])['files'][0]['path']==str(target)


def test_metadata_locks_preserve_personal_rating(library):
    work_id=add_work(library,'Locked')
    library.update_personal(work_id,rating=7)
    library.edit_metadata(work_id,{'title':'User title','actors':[{'name':'A','gender':'unknown'}]},['title','actors'])
    assert library.work(work_id)['rating']==7
    assert library.actresses()==[]
