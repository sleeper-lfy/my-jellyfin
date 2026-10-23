import json
from pathlib import Path
import pytest
from lumen import core
from lumen.core import identity,now
from lumen.media_tools import add_bookmark


def files(folder,names):
    folder.mkdir(parents=True,exist_ok=True)
    result=[]
    for index,name in enumerate(names):
        path=folder/name;path.write_bytes((str(path)+' different content '+str(index)).encode());result.append(path)
    return result


@pytest.mark.parametrize('fast',[False,True])
def test_folder_is_one_show_and_release_names_are_accepted(library,tmp_path,monkeypatch,fast):
    monkeypatch.setattr(core,'probe',lambda path:30);monkeypatch.setattr(core,'thumbnail',lambda *args:None)
    root=tmp_path/'shows'
    videos=files(root/'漂流記',['[Studio] 15漂流記 OVA 1 [DVD-4285].mp4','[Studio] 15漂流記 OVA 2 ～特別編～ [DVD-481].mp4'])
    files(root/'另一部剧',['[Studio] 名称 第1巻 [DISC-57678].mp4','完全没有编号.mp4'])
    result=library.import_folder(root,'series',fast=fast)
    assert result['imported']==4 and not result['errors'],result
    shows=library.query();assert len(shows)==2
    show=next(show for show in shows if show['title']=='漂流記');assert [row['episode'] for row in show['files']]==[1,2]
    assert {Path(row['path']) for row in show['files']}==set(videos)
    again=library.import_folder(root,'series',fast=fast);assert again['duplicates']==4 and not again['errors']
    assert len(library.query())==2


def test_unknown_episodes_use_natural_order_without_stealing_nfo_numbers(library,tmp_path):
    folder=tmp_path/'自然排序';videos=files(folder,['片段10.mp4','片段2.mp4','片段1.mp4','特辑.mp4'])
    (folder/'特辑.nfo').write_text('<episodedetails><title>Special</title><season>1</season><episode>2</episode></episodedetails>')
    assert library.import_folder(folder,'series',fast=True)['imported']==4
    show=library.query()[0];numbers={Path(row['path']).stem:row['episode'] for row in show['files']}
    assert numbers=={'片段1':1,'特辑':2,'片段2':3,'片段10':4}
    new=files(folder,['A新增无编号.mp4'])[0]
    result=library.import_folder(folder,'series',fast=True);assert result['imported']==1 and not result['errors']
    updated={Path(row['path']).stem:row['episode'] for row in library.work(show['id'])['files']}
    assert all(updated[name]==number for name,number in numbers.items());assert updated[new.stem]==5


def test_nfo_and_seasons_override_numbers_but_titles_never_split_folder(library,tmp_path):
    show=tmp_path/'Folder title';videos=files(show/'Season 1',['Different.S01E01.mp4','Unrelated.S01E02.mp4'])
    files(show/'Season 2',['Opaque.mp4'])
    (show/'tvshow.nfo').write_text('<tvshow><title>整剧名称</title><year>2020</year></tvshow>')
    videos[0].with_suffix('.nfo').write_text('<episodedetails><title>单集名称</title><season>0</season><episode>8</episode></episodedetails>')
    result=library.import_folder(show,'series',fast=True);assert result['imported']==3 and not result['errors'],result
    shows=library.query();assert len(shows)==1 and shows[0]['title']=='整剧名称'
    episodes=library.work(shows[0]['id'])['files'];assert {(row['season'],row['episode']) for row in episodes}=={(0,8),(1,2),(2,1)}
    assert next(row for row in episodes if row['season']==0)['title']=='单集名称'


def test_identical_titles_in_different_folders_do_not_merge(library,tmp_path):
    for name in ('a','b'):
        folder=tmp_path/name/'相同名称';files(folder,['opaque.mp4'])
        (folder/'tvshow.nfo').write_text('<tvshow><title>Same display title</title></tvshow>')
    result=library.import_folder(tmp_path,'series',fast=True);assert result['imported']==2 and not result['errors'],result
    assert len(library.query())==2


def test_retry_only_failed_paths_joins_old_folder_and_preserves_numbers(library,tmp_path):
    folder=tmp_path/'Legacy';first,second=files(folder,['First.S01E02.mp4','无编号.mp4'])
    library.import_folder(folder,'series',fast=True,candidates=[first]);show=library.query()[0]
    # Simulate an older installation without folder bindings.
    library.db.execute("DELETE FROM name_keys WHERE key LIKE 'series-folder:%'");library.db.commit()
    result=library.import_folder(folder,'series',fast=True,candidates=[second])
    assert result['imported']==1 and not result['errors'];assert len(library.query())==1
    assert {row['episode'] for row in library.work(show['id'])['files']}=={1,2}


def test_rescan_regroups_old_split_show_without_losing_file_history(library,tmp_path):
    folder=tmp_path/'One show';videos=files(folder,['Alpha.S01E01.mp4','Beta.S01E02.mp4'])
    ids=[]
    for index,video in enumerate(videos,1):
        with library.db:
            work=library.db.execute('INSERT INTO works(identity,kind,title,added) VALUES (?,?,?,?)',(identity(video.stem,None,'series'),'series',video.stem,now())).lastrowid
            file=library.db.execute('INSERT INTO files(work_id,path,digest,root,season,episode,duration,position) VALUES (?,?,?,?,?,?,?,?)',(work,str(video),'legacy'+str(index),str(folder),1,index,30,index*2)).lastrowid
            metadata={'episode_details':{str(file):{'title':'Episode '+str(index)}},'episode_stills':{str(file):['image'+str(index)]}}
            library.db.execute('UPDATE works SET metadata=?,favorite=? WHERE id=?',(json.dumps(metadata),int(index==2),work))
            ids.append(file)
    bookmark=add_bookmark(library,ids[1],4,'Keep bookmark')
    result=library.import_folder(folder,'series',fast=True)
    assert result['duplicates']==2 and not result['errors'],result
    shows=library.query();assert len(shows)==1 and shows[0]['favorite']==1
    show=library.work(shows[0]['id']);assert [row['id'] for row in show['files']]==ids
    assert [row['position'] for row in show['files']]==[2,4]
    assert len(show['metadata']['episode_details'])==len(show['metadata']['episode_stills'])==2
    assert library.db.execute('SELECT file_id FROM bookmarks WHERE id=?',(bookmark['id'],)).fetchone()[0]==ids[1]


def test_unchanged_series_rescan_never_reopens_nfo(library,tmp_path,monkeypatch):
    from lumen import nfo
    folder=tmp_path/'Cached';video=files(folder,['opaque.mp4'])[0]
    video.with_suffix('.nfo').write_text('<episodedetails><title>Episode</title><season>1</season><episode>8</episode></episodedetails>')
    assert library.import_folder(folder,'series',fast=True)['imported']==1
    monkeypatch.setattr(nfo,'read',lambda *args:pytest.fail('Unchanged NFO must not be reparsed'))
    result=library.import_folder(folder,'series',fast=True);assert result['duplicates']==1 and not result['errors']


def test_partial_retry_reserves_numbers_of_unselected_existing_files(library,tmp_path):
    folder=tmp_path/'Retry';first=files(folder,['无编号甲.mp4'])[0]
    library.import_folder(folder,'series',fast=True);second=files(folder,['无编号乙.mp4'])[0]
    result=library.import_folder(folder,'series',fast=True,candidates=[second]);assert result['imported']==1 and not result['errors']
    show=library.query()[0];assert {row['episode'] for row in show['files']}=={1,2}
