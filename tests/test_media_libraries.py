import json
from pathlib import Path
import pytest
from lumen import media_libraries as ml
from lumen.core import Library


def cfg(*roots,**rule):
    return {'roots':[{'path':str(root),'enabled':True} for root in roots],**rule}


def video(root,name='Shared.2024.mp4',content=b'video'):
    root.mkdir(parents=True,exist_ok=True);path=root/name;path.write_bytes(content);return path


def test_named_library_multiple_roots_independent_rules_and_reopen(library,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';x=ml.save(library,'我的电影','movie',cfg(a,b,plugin='provider-a',fallback_plugins=['provider-b'],naming={'filename':'{title}'}))
    other=ml.save(library,'另一电影库','movie',cfg(tmp_path/'c',plugin='provider-c'))
    assert x['config']['plugin']=='provider-a' and other['config']['plugin']=='provider-c'
    connection=Library(library.directory,initialize=False)
    try:assert len(ml.get(connection,x['id'])['config']['roots'])==2
    finally:connection.close()
    assert {r['id']:(r['name'],r['kind'],r['count']) for r in ml.list_libraries(library,public=True)}=={x['id']:('我的电影','movie',0),other['id']:('另一电影库','movie',0)}


def test_conflicts_names_types_nested_sources_and_destinations(library,tmp_path):
    one=ml.save(library,'电影','movie',cfg(tmp_path/'a',destination=str(tmp_path/'organized')))
    for path in [tmp_path/'a',tmp_path/'a'/'sub',tmp_path/'organized'/'sub']:
        with pytest.raises(ValueError,match='重叠'):ml.save(library,'冲突','movie',cfg(path))
    with pytest.raises(ValueError,match='名称'):ml.save(library,'电影','vr',cfg(tmp_path/'b'))
    with pytest.raises(ValueError,match='类型'):ml.save(library,'电影','vr',cfg(tmp_path/'a'),one['id'])
    with pytest.raises(ValueError):ml.save(library,'相对路径','movie',cfg('relative'))
    with pytest.raises(ValueError):ml.save(library,'重复','movie',cfg(tmp_path/'b',tmp_path/'b'/'c'))
    assert len(ml.list_libraries(library))==1


def test_shared_work_copies_are_file_scoped_in_browse_facets_watch_and_shuffle(library,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';video(a);video(b)
    left=ml.save(library,'A','movie',cfg(a));right=ml.save(library,'B','movie',cfg(b))
    library.import_folder(a,'movie',fast=True);library.import_folder(b,'movie',fast=True)
    all_items=library.query();assert len(all_items)==1 and len(all_items[0]['files'])==2
    work=all_items[0];library.update_personal(work['id'],rating=8,favorite=True)
    f=library.work(work['id'],left['id'])['files'][0]
    with library.db:library.db.execute('UPDATE files SET completed=1,position=20 WHERE id=?',(f['id'],))
    assert library.query({'media_library_id':left['id'],'watch_state':'completed'})
    assert not library.query({'media_library_id':right['id'],'watch_state':'completed'})
    scoped=library.query({'media_library_id':right['id'],'local':False})
    assert len(scoped)==1 and len(scoped[0]['files'])==1 and scoped[0]['files'][0]['path'].startswith(str(b))
    assert scoped[0]['rating']==8 and scoped[0]['favorite']==1
    assert library.shuffle({'media_library_id':left['id']})['filters']['media_library_id']==left['id']
    assert library.filter_options(media_library_id=right['id'])['years']==[2024]


def test_remove_retains_files_progress_favorites_and_global_visibility(library,tmp_path):
    root=tmp_path/'videos';path=video(root);item=ml.save(library,'电影','movie',cfg(root));library.import_folder(root,'movie',fast=True)
    work=library.query()[0];library.update_personal(work['id'],favorite=True,rating=9)
    with library.db:library.db.execute('UPDATE files SET position=123 WHERE work_id=?',(work['id'],))
    ml.remove(library,item['id'])
    assert path.exists() and library.work(work['id'])['files'][0]['position']==123
    assert library.work(work['id'])['favorite'] and library.work(work['id'])['rating']==9
    assert not ml.list_libraries(library)
    with pytest.raises(ValueError):library.query({'media_library_id':item['id']})


def test_explicit_legacy_migration_preserves_effective_directory_overrides(library,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';video(a,content=b'a');video(b,content=b'b')
    library.import_folder(a,'movie',fast=True);library.import_folder(b,'movie',fast=True)
    library.set_setting('watched_folders',[{'path':str(a),'kind':'movie','enabled':False,'plugin':'directory-engine'}])
    library.set_setting('partition:movie',{'plugin':'default-engine'})
    library.set_setting('numbered_fallbacks:movie',['fallback'])
    assert not ml.list_libraries(library)
    ids=ml.migrate_legacy(library);assert len(ids)==2
    migrated=next(x for x in ml.list_libraries(library) if x['config']['roots'])
    assert migrated['config']['plugin']=='directory-engine' and migrated['config']['fallback_plugins']==['fallback']
    assert not migrated['config']['roots'][0]['enabled']
    assert library.setting('watched_folders')==[] and ml.migrate_legacy(library)==[]
    assert sum(x['count'] for x in ml.list_libraries(library))==2


def test_schema_two_upgrades_with_backup_without_touching_personal_data(library):
    with library.db:
        library.db.execute('DROP TABLE media_library_files');library.db.execute('DROP TABLE media_libraries');library.db.execute('PRAGMA user_version=2')
    other=Library(library.directory)
    try:assert other.db.execute('PRAGMA user_version').fetchone()[0]==3
    finally:other.close()
    assert list((library.directory/'backups').glob('schema-2-to-3-*.sqlite'))


def test_scan_uses_each_library_source_fallback_and_naming_and_moves_only_its_files(library,tmp_path,monkeypatch):
    from lumen import ingestion
    a,b=tmp_path/'a',tmp_path/'b';video(a);video(b)
    left=ml.save(library,'A','movie',cfg(a,plugin='a',fallback_plugins=['a-backup'],destination=str(tmp_path/'out-a'),naming={'filename':'A-{title}'}))
    right=ml.save(library,'B','movie',cfg(b,plugin='b',destination=str(tmp_path/'out-b'),naming={'filename':'B-{title}'}))
    library.import_folder(a,'movie',fast=True);library.import_folder(b,'movie',fast=True);calls=[]
    def resolve(lib,work,primary,fallbacks,cancelled):
        calls.append((primary,fallbacks,[f['path'] for f in work['files']]))
        return {'plugin':primary,'candidate':{},'attempts':[]}
    monkeypatch.setattr('lumen.numbered_sources.resolve',resolve)
    monkeypatch.setattr(ingestion,'Plugins',lambda lib:type('Manager',(),{'merge':lambda *a:None})())
    work=library.query()[0];ingestion.enqueue(library,work,'global','')
    assert ingestion.process_pending(library,media_library_id=left['id'])['completed']==1
    assert calls[0][0:2]==('a',['a-backup']) and len(calls[0][2])==1
    assert (b/'Shared.2024.mp4').exists() and not (a/'Shared.2024.mp4').exists()
    moved=library.work(work['id'],left['id'])['files'][0];assert Path(moved['path']).name=='A-Shared.mp4'
    assert ingestion.process_pending(library,media_library_id=right['id'])['completed']==1
    assert calls[1][0]=='b' and Path(library.work(work['id'],right['id'])['files'][0]['path']).name=='B-Shared.mp4'
    assert len(library.work(work['id'])['files'])==2


def test_watch_pause_manual_scan_and_membership_survive_unavailable_root(library,tmp_path):
    import os,time
    from lumen.media_tools import watch_folders
    a,b=tmp_path/'a',tmp_path/'b';p=video(a,content=b'a');q=video(b,content=b'b')
    stamp=time.time()-100;os.utime(p,(stamp,stamp));os.utime(q,(stamp,stamp))
    item=ml.save(library,'目录监听','movie',{'roots':[{'path':str(a),'enabled':True},{'path':str(b),'enabled':False}],'settle_seconds':5})
    watch_folders(library,clock=lambda:stamp+50);result=watch_folders(library,clock=lambda:stamp+60)
    assert result['imported']==1 and len(library.query({'media_library_id':item['id']}))==1
    # Paused folders are still included in an explicitly requested scan.
    result=ml.scan(library,item['id']);assert result['imported']==1
    original=library.query({'media_library_id':item['id']});p.unlink();a.rmdir()
    result=ml.scan(library,item['id']);assert result['offline'] and len(library.query({'media_library_id':item['id']}))==len(original)


def test_library_backup_restore_includes_configs_memberships_and_personal_state(library,tmp_path):
    from lumen.backup import restore_database
    root=tmp_path/'videos';video(root);item=ml.save(library,'家庭电影','movie',cfg(root))
    library.import_folder(root,'movie',fast=True);work=library.query()[0];library.update_personal(work['id'],rating=7,favorite=True)
    backup=tmp_path/'complete.sqlite';library.backup(backup);ml.remove(library,item['id'])
    restore_database(library,backup)
    assert ml.get(library,item['id'])['name']=='家庭电影'
    result=library.query({'media_library_id':item['id']});assert len(result)==1 and result[0]['rating']==7 and result[0]['favorite']==1


def test_fixed_library_kind_cannot_be_changed_through_work_actions(library,tmp_path):
    root=tmp_path/'movies';video(root);item=ml.save(library,'电影','movie',cfg(root));library.import_folder(root,'movie',fast=True)
    work=library.query()[0]
    with pytest.raises(ValueError,match='固定类型'):library.set_movie_kind(work['id'],'vr')
    assert library.work(work['id'])['kind']=='movie'
    ml.remove(library,item['id']);library.set_movie_kind(work['id'],'vr');assert library.work(work['id'])['kind']=='vr'


def test_migration_groups_equal_rules_but_preserves_overrides_with_shared_output(library,tmp_path):
    a,b,c=[tmp_path/name for name in ['a','b','c']];target=tmp_path/'archive'
    library.set_setting('partition:movie',{'plugin':'same','destination':str(target)})
    library.set_setting('watched_folders',[{'kind':'movie','path':str(a)},{'kind':'movie','path':str(b),'enabled':False},{'kind':'movie','path':str(c),'plugin':'different'}])
    ids=ml.migrate_legacy(library);assert len(ids)==2
    configs=[ml.get(library,i)['config'] for i in ids]
    shared=next(x for x in configs if x['plugin']=='same');assert len(shared['roots'])==2 and shared['roots'][1]['enabled'] is False
    assert all(x['destination']==str(target) for x in configs)
    assert ml.owner_for_path(library,target/'unknown.mp4','movie') is None
    assert ml.owner_for_path(library,c/'new.mp4','movie')==next(i for i in ids if ml.get(library,i)['config']['plugin']=='different')


def test_migration_adopts_already_organized_files_only_when_output_owner_is_unique(library,tmp_path):
    archive=tmp_path/'archive';video(archive);library.import_folder(archive,'movie',fast=True)
    library.set_setting('partition:movie',{'destination':str(archive)})
    library.set_setting('watched_folders',[{'kind':'movie','path':str(tmp_path/'incoming')}])
    ids=ml.migrate_legacy(library);assert len(ids)==1 and len(library.query({'media_library_id':ids[0]}))==1


def test_batch_watched_and_detach_only_affect_selected_library_files(library,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';video(a);video(b)
    left=ml.save(library,'A','movie',cfg(a));right=ml.save(library,'B','movie',cfg(b))
    library.import_folder(a,'movie',fast=True);library.import_folder(b,'movie',fast=True)
    work=library.query()[0];library.update_personal(work['id'],rating=8,favorite=True)
    library.batch_catalog([work['id']],'completed',media_library_id=left['id'])
    assert library.work(work['id'],left['id'])['files'][0]['completed']==1
    assert library.work(work['id'],right['id'])['files'][0]['completed']==0
    ml.detach_work(library,left['id'],work['id'])
    assert not library.query({'media_library_id':left['id']})
    assert library.work(work['id'],right['id'])['favorite']==1 and library.work(work['id'])['rating']==8
    assert len(library.work(work['id'])['files'])==2


def test_manual_confirmation_keeps_other_library_pipeline_pending(library,tmp_path):
    import json
    from lumen import ingestion
    a,b=tmp_path/'a',tmp_path/'b';video(a);video(b)
    left=ml.save(library,'A','movie',cfg(a,plugin='first'));right=ml.save(library,'B','movie',cfg(b,plugin='second'))
    library.import_folder(a,'movie',fast=True);library.import_folder(b,'movie',fast=True)
    work=library.query()[0];ingestion.enqueue(library,work,'global','')
    with library.db:library.db.execute("UPDATE tasks SET status='pending' WHERE kind='ingest'")
    ingestion.confirm(library,work['id'],left['id'])
    tasks={json.loads(row['payload'])['media_library_id']:dict(row) for row in library.db.execute("SELECT * FROM tasks WHERE kind='ingest'")}
    assert tasks[left['id']]['status']=='queued' and json.loads(tasks[left['id']]['payload'])['stage']=='organize'
    assert tasks[right['id']]['status']=='pending' and json.loads(tasks[right['id']]['payload'])['stage']=='identify'
    ingestion.confirm(library,work['id'])
    assert library.db.execute('SELECT status FROM tasks WHERE id=?',(tasks[right['id']]['id'],)).fetchone()[0]=='pending'


def test_manually_mixed_queue_can_play_work_outside_original_library(library,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';video(a,'First.2024.mp4');video(b,'Second.2024.mp4')
    left=ml.save(library,'A','movie',cfg(a));right=ml.save(library,'B','movie',cfg(b))
    library.import_folder(a,'movie',fast=True);library.import_folder(b,'movie',fast=True)
    queue=library.shuffle({'media_library_id':left['id']});first=queue['ids'][0];second=library.query({'media_library_id':right['id']})[0]['id']
    assert library.edit_queue([first])['filters']['media_library_id']==left['id']
    mixed=library.edit_queue([first,second]);assert 'media_library_id' not in mixed['filters']
    assert library.queue_step(1)==second and library.resume_file(second,media_library_id=mixed['filters'].get('media_library_id'))['path'].startswith(str(b))
