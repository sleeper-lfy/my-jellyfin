import json
import pytest
from lumen.core import Library
from lumen.merge_history import preview_merge,apply_merge,undo_merge,records,state
from test_core import add_work
from lumen.media_tools import add_bookmark


def test_preview_writes_nothing_and_reports_real_inheritance(library):
    target=add_work(library,'Target',metadata={'tags':['Target tag']});source=add_work(library,'Source',metadata={'overview':'Fill missing'})
    library.update_personal(source,rating=8,watchlist=True)
    before=state(library,[target,source])
    preview=preview_merge(library,[source],target)
    assert preview['result']['title']=='Target' and preview['result']['rating']==8
    assert len(preview['result']['files'])==2 and preview['result']['metadata']['overview']=='Fill missing'
    assert state(library,[target,source])==before and not records(library,target)


def test_undo_survives_restart_and_keeps_new_playback_and_unrelated_changes(tmp_path):
    library=Library(tmp_path/'data');target=add_work(library,'Target');source=add_work(library,'Source')
    add_work(library,'Existing unrelated')
    library.update_personal(target,rating=9,favorite=True);library.update_personal(source,rating=7,watchlist=True)
    original=state(library,[target,source]);file=library.work(source)['files'][0]
    bookmark=add_bookmark(library,file['id'],10,'Before merge')
    queue={'ids':[source,target],'index':0};library.set_setting('queue',queue)
    result=apply_merge(library,preview_merge(library,[source],target));library.close()
    library=Library(tmp_path/'data')
    with library.db:library.db.execute('UPDATE files SET position=45,completed=1 WHERE id=?',(file['id'],))
    other=add_work(library,'Unrelated');library.update_personal(other,rating=10)
    undo_merge(library,result['merge_id'])
    assert state(library,[target,source])==original
    restored=library.work(source)['files'][0];assert restored['id']==file['id'] and restored['position']==45 and restored['completed']==1
    assert library.db.execute('SELECT file_id FROM bookmarks WHERE id=?',(bookmark['id'],)).fetchone()[0]==file['id']
    assert library.work(other)['rating']==10 and library.setting('queue')==queue
    assert records(library,target)[0]['status']=='undone'
    with pytest.raises(ValueError,match='已经撤销'):undo_merge(library,result['merge_id'])
    library.close()


@pytest.mark.parametrize('change',['metadata','membership','artwork','reused_id'])
def test_undo_conflicts_never_overwrite_new_data(library,change):
    target=add_work(library,'Target');source=add_work(library,'Source')
    result=apply_merge(library,preview_merge(library,[source],target))
    if change=='metadata':library.edit_metadata(target,{'overview':'New edit'},[])
    elif change=='membership':
        with library.db:library.db.execute('UPDATE files SET path=path||? WHERE work_id=?',('.moved',target))
    elif change=='artwork':library.set_setting(f'artwork_{target}',{'poster':'new.jpg'})
    else:assert add_work(library,'Reused ID')==source
    before=state(library,[target,source])
    with pytest.raises(ValueError,match='无法安全撤销'):undo_merge(library,result['merge_id'])
    assert state(library,[target,source])==before and records(library,target)[0]['status']=='merged'


def test_preview_staleness_and_failed_merge_are_atomic(library):
    target=add_work(library,'Target');source=add_work(library,'Source')
    preview=preview_merge(library,[source],target);library.update_personal(source,rating=6)
    before=state(library,[target,source])
    with pytest.raises(ValueError,match='预览后'):apply_merge(library,preview)
    assert state(library,[target,source])==before and not records(library,target)
    series=add_work(library,'Series',kind='series')
    with pytest.raises(ValueError):preview_merge(library,[source,series],target)
    assert state(library,[target,source])==before


def test_fans_multi_merge_preview_and_undo_restore_roots_and_creator(library):
    ids=[add_work(library,'Author '+str(i),kind='fans',metadata={'creator':'Author '+str(i),'fans_roots':['/authors/'+str(i)]}) for i in range(3)]
    before=state(library,ids)
    preview=preview_merge(library,ids[1:],ids[0],'Unified author')
    assert preview['result']['title']=='Unified author' and len(preview['result']['files'])==3
    assert len(preview['result']['metadata']['fans_roots'])==3 and state(library,ids)==before
    result=apply_merge(library,preview);assert len(library.query())==1
    undo_merge(library,result['merge_id']);assert state(library,ids)==before


def test_undo_keeps_a_queue_edited_after_merge(library):
    target=add_work(library,'Target');source=add_work(library,'Source')
    result=apply_merge(library,preview_merge(library,[source],target))
    queue={'ids':[target],'index':0,'repeat':'all'};library.set_setting('queue',queue)
    undo_merge(library,result['merge_id']);assert library.setting('queue')==queue


def test_undo_late_identity_collision_rolls_back_every_table(library):
    target=add_work(library,'Target');source=add_work(library,'Source');add_work(library,'Anchor')
    result=apply_merge(library,preview_merge(library,[source],target))
    other=add_work(library,'Source',local=False);assert other!=source
    before=state(library,[target,source,other])
    with pytest.raises(ValueError,match='索引已被占用'):undo_merge(library,result['merge_id'])
    assert state(library,[target,source,other])==before


def test_chained_merges_can_be_undone_in_reverse_order(library):
    target=add_work(library,'Target');first=add_work(library,'First');second=add_work(library,'Second')
    original=state(library,[target,first,second])
    a=apply_merge(library,preview_merge(library,[first],target))
    b=apply_merge(library,preview_merge(library,[second],target))
    with pytest.raises(ValueError,match='无法安全撤销'):undo_merge(library,a['merge_id'])
    undo_merge(library,b['merge_id']);undo_merge(library,a['merge_id'])
    assert state(library,[target,first,second])==original
