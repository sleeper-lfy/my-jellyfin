import json
import shutil
import pytest
from pathlib import Path
from test_core import add_work
from lumen.core import fingerprint


def test_sort_full_result_before_pagination_and_nulls_last(library):
    z=add_work(library,'Zulu',year=None);a=add_work(library,'Alpha',year=2020);b=add_work(library,'Beta',year=2024)
    assert [w['id'] for w in library.query({'sort':'title','descending':False},1,1)]==[b]
    assert [w['id'] for w in library.query({'sort':'year'})]==[b,a,z]
    with pytest.raises(ValueError):library.query({'sort':'title; DROP TABLE works'})


def test_manual_status_does_not_fabricate_or_erase_history(library):
    w=add_work(library,'Status');f=library.work(w)['files'][0]
    with library.db:
        library.db.execute("INSERT INTO sessions VALUES ('real',?,'2026-01-01','2026-01-01',123)",(f['id'],))
        library.db.execute('UPDATE files SET position=23 WHERE id=?',(f['id'],))
    assert library.query({'watch_state':'progress'})[0]['id']==w
    library.set_watched(w,'completed')
    assert library.query({'watch_state':'completed'})[0]['id']==w
    library.set_watched(w,'unwatched')
    assert library.query({'watch_state':'unwatched'})[0]['id']==w
    assert library.db.execute("SELECT watched FROM sessions WHERE id='real'").fetchone()[0]==123


def test_batch_validation_and_queue_preserves_current(library):
    ids=[add_work(library,n) for n in ['A','B','C']]
    library.batch_catalog(ids,'favorite',True);assert len(library.query({'favorite':True}))==3
    library.batch_catalog(ids,'tags',['tag']);assert len(library.query({'tags_all':['tag']}))==3
    with pytest.raises(ValueError):library.batch_catalog([ids[0],999999],'favorite',False)
    assert library.work(ids[0])['favorite']==1
    library.edit_queue(ids);q=library.setting('queue');q['index']=1;library.set_setting('queue',q)
    q=library.edit_queue(list(reversed(ids)),'all');assert q['ids'][q['index']]==ids[1]
    q=library.edit_queue([ids[2],ids[1]],'all');assert library.queue_step(1)==ids[2]
    with pytest.raises(ValueError):library.edit_queue([99999])


def test_remove_catalog_keeps_source_but_removes_related_rows(library,tmp_path):
    w=add_work(library,'Remove');source=tmp_path/'keep.mp4';source.write_bytes(b'media')
    with library.db:library.db.execute('UPDATE files SET path=? WHERE work_id=?',(str(source),w))
    file=library.work(w)['files'][0]
    with library.db:
        library.db.execute("INSERT INTO sessions VALUES ('ended',?,'2026-01-01','2026-01-01',9)",(file['id'],))
        library.db.execute("INSERT INTO activity VALUES ('ended','2026-01-01',9)")
        library.db.execute("INSERT INTO bookmarks VALUES ('mark',?,10,'point','','','2026-01-01')",(file['id'],))
    library.edit_queue([w]);library.remove_catalog(w)
    assert library.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
    assert library.db.execute('SELECT COUNT(*) FROM bookmarks').fetchone()[0]==0
    assert source.read_bytes()==b'media';assert not library.query();assert library.setting('queue')['ids']==[]


def test_relocate_verifies_all_files_before_commit_preserves_ids(library,tmp_path):
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir()
    ids=[add_work(library,name) for name in ['One','Two']]
    for i,w in enumerate(ids):
        source=old/f'{i}.mp4';source.write_bytes(bytes([i])*1024);shutil.copyfile(source,new/source.name)
        with library.db:library.db.execute('UPDATE files SET path=?,root=?,digest=?,position=42 WHERE work_id=?',(str(source),str(old),fingerprint(source),w))
    (new/'1.mp4').write_bytes(b'wrong')
    with pytest.raises(ValueError,match='校验'):library.relocate_root(old,new)
    assert all(Path(library.work(w)['files'][0]['path']).parent==old for w in ids)
    shutil.copyfile(old/'1.mp4',new/'1.mp4')
    before=[library.work(w)['files'][0]['id'] for w in ids]
    assert library.relocate_root(old,new)['relocated']==2
    assert [library.work(w)['files'][0]['id'] for w in ids]==before
    assert all(library.work(w)['files'][0]['position']==42 for w in ids)
    assert all(Path(library.work(w)['files'][0]['path']).parent==new for w in ids)


def test_season_selector_and_batch_click_do_not_open_details(qapp,library,tmp_path):
    from lumen.ui import MainWindow,Details
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w=add_work(library,'Series','series');f=library.work(w)['files'][0]
    with library.db:library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',(w,'/media/second.mp4','second','/media',100,2,1))
    window=MainWindow(library.directory);window.navigate('series');window.resize(1280,900);window.show()
    detail=Details(window,w);assert detail.season_filter.count()==3
    detail.season_filter.setCurrentIndex(2)
    assert detail.files.item(0).isHidden() and not detail.files.item(1).isHidden()
    window.select_catalog_mode(True);assert window.cards.property('batchMode')
    window.close()


def test_fullscreen_still_viewer_navigation_and_player_settings(qapp,library,tmp_path):
    from PySide6.QtGui import QImage,QColor
    from lumen.catalog_ui import StillViewer
    from lumen.player import Player
    paths=[]
    for i in range(2):
        path=tmp_path/f'still{i}.png';image=QImage(640,360,QImage.Format.Format_RGB32);image.fill(QColor('blue' if i else 'red'));image.save(str(path));paths.append(path)
    viewer=StillViewer(paths);qapp.processEvents();assert len(viewer.scene.items())==1
    viewer.step(1);assert viewer.index==1 and len(viewer.scene.items())==1;viewer.close()
    player=Player(library);player.playback_speed.setCurrentIndex(player.playback_speed.findData(1.5));assert player.media.playbackRate()==1.5
    player.auto_next.setChecked(False);assert library.setting('auto_next') is False;player.close()
