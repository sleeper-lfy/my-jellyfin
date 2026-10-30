from pathlib import Path
import pytest
from lumen import core
from lumen.core import identity,now
from lumen.media_tools import add_bookmark
from test_series_folders import files


@pytest.mark.parametrize('fast',[True,False])
def test_same_vr_folder_is_one_work_and_children_stay_separate(library,tmp_path,monkeypatch,fast):
    monkeypatch.setattr(core,'probe',lambda path:30);monkeypatch.setattr(core,'thumbnail',lambda *args:None)
    root=tmp_path/'VR';folder=root/'Feature'
    videos=files(folder,['Part10.mp4','Part2.mp4','Part1.mp4'])
    files(folder/'Bonus',['Scene1.mp4','Scene2.mp4']);files(root/'Other',['Other.mp4'])
    result=library.import_folder(root,'vr',fast=fast)
    assert result['imported']==6 and not result['errors'],result
    works=library.query({'kinds':['vr']});assert len(works)==3
    film=next(work for work in works if work['title']=='Feature')
    assert [Path(file['path']).name for file in film['files']]==['Part1.mp4','Part2.mp4','Part10.mp4']
    assert {Path(file['path']) for file in film['files']}==set(videos)
    again=library.import_folder(root,'vr',fast=fast)
    assert again['duplicates']==6 and not again['errors'] and len(library.query())==3


def test_partial_import_and_scraped_title_keep_vr_folder_binding(library,tmp_path):
    folder=tmp_path/'Film';first=files(folder,['Part1.mp4'])[0]
    assert library.import_folder(folder,'vr',fast=True)['imported']==1
    film=library.query()[0]
    library.edit_metadata(film['id'],{'title':'Scraped title'},[])
    second=files(folder,['Unrelated filename.mp4'])[0]
    result=library.import_folder(tmp_path,'vr',fast=True,candidates=[second])
    assert result['imported']==1 and not result['errors'] and len(library.query())==1
    current=library.work(film['id']);assert current['title']=='Scraped title'
    assert {Path(file['path']) for file in current['files']}=={first,second}


def test_rescan_groups_legacy_vr_splits_without_losing_records(library,tmp_path):
    folder=tmp_path/'Legacy';videos=files(folder,['A.mp4','B.mp4']);ids=[]
    for index,path in enumerate(videos):
        with library.db:
            work=library.db.execute('INSERT INTO works(identity,kind,title,added,favorite) VALUES (?,?,?,?,?)',(identity(path.stem,None,'vr'),'vr',path.stem,now(),index)).lastrowid
            file=library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,position) VALUES (?,?,?,?,?,?)',(work,str(path),'legacy'+str(index),str(folder),30,index+2)).lastrowid;ids.append(file)
    bookmark=add_bookmark(library,ids[1],4,'Keep')
    result=library.import_folder(folder,'vr',fast=True)
    assert result['duplicates']==2 and not result['errors'],result
    works=library.query();assert len(works)==1 and works[0]['favorite']==1
    assert [file['id'] for file in works[0]['files']]==ids
    assert [file['position'] for file in works[0]['files']]==[2,3]
    assert library.db.execute('SELECT file_id FROM bookmarks WHERE id=?',(bookmark['id'],)).fetchone()[0]==ids[1]


def test_separate_directories_with_same_nfo_title_stay_separate(library,tmp_path):
    for part in ['one','two']:
        folder=tmp_path/part/'Same folder name';files(folder,['Opaque.mp4'])
        (folder/'movie.nfo').write_text('<movie><title>Same film title</title></movie>',encoding='utf-8')
    result=library.import_folder(tmp_path,'vr',fast=True)
    assert result['imported']==2 and not result['errors'],result
    assert len(library.query())==2 and all(work['title']=='Same film title' for work in library.query())
