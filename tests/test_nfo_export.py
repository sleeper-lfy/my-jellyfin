import copy
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from PySide6.QtGui import QImage,QColor
from lumen.core import ImportCancelled
from lumen import nfo
from lumen.nfo_export import plan_export, preview_export, export_works, _publish


def media(library,tmp_path,kind='movie',name='Film.2024.mp4'):
    folder=tmp_path/'media';folder.mkdir(exist_ok=True)
    video=folder/name;video.write_bytes(name.encode())
    library.import_folder(folder,kind,fast=True)
    work=library.query({'kinds':[kind]})[0]
    library.edit_metadata(work['id'],{'title':'标题 & 特别版','year':2024,'overview':'手写简介 <保留>','tags':['手动标签','另一个'],
        'actors':[{'name':'演员甲','gender':'unknown','aliases':['别名'],'role':'主演'}],
        'external_ids':{'imdb':'tt1234567','tmdb':'123'},'custom_field':'keep'},['actors','tags'])
    library.update_personal(work['id'],rating=9,favorite=True)
    with library.db:
        library.db.execute('UPDATE files SET position=23.5,duration=100,completed=1 WHERE work_id=?',(work['id'],))
    return video,work['id']


def picture(path):
    image=QImage(40,60,QImage.Format.Format_RGB32);image.fill(QColor('red'));assert image.save(str(path),'PNG');return path


def test_movie_roundtrip_preserves_manual_metadata_and_does_not_change_library(library,tmp_path,qapp):
    video,identifier=media(library,tmp_path)
    original=[tuple(row) for row in library.db.execute('SELECT * FROM works')]
    result=export_works(library,[identifier],images=False)
    assert result['written']==1 and not result['errors']
    sidecar=video.with_suffix('.nfo');read=nfo.read(sidecar)
    assert read['metadata']['title']=='标题 & 特别版'
    assert read['metadata']['tags']==['手动标签','另一个']
    assert read['metadata']['actors'][0]['gender']=='unknown'
    assert read['metadata']['actors'][0]['name']=='演员甲'
    assert read['metadata']['external_ids']=={'imdb':'tt1234567','tmdb':'123'}
    assert read['userrating']==9 and read['completed'] and read['position']==23.5
    assert ET.parse(sidecar).findtext('actor/alias')=='别名'
    assert [tuple(row) for row in library.db.execute('SELECT * FROM works')]==original
    assert video.read_bytes()==video.name.encode()


def test_existing_is_skipped_by_default_then_updated_with_backup_and_unknown_fields(library,tmp_path):
    video,identifier=media(library,tmp_path)
    sidecar=video.with_suffix('.nfo')
    before=b'<?xml version="1.0"?><movie><!--keep--><title>Old</title><custom key="value">Unknown</custom><actor><name>actor</name><extra>actor extra</extra></actor><tag>old</tag></movie>'
    sidecar.write_bytes(before)
    result=export_works(library,[identifier],images=False)
    assert result['skipped']==1 and sidecar.read_bytes()==before
    result=export_works(library,[identifier],overwrite=True,images=False)
    assert result['written']==1 and len(result['backups'])==1
    assert Path(result['backups'][0]).read_bytes()==before
    tree=ET.parse(sidecar)
    assert tree.findtext('custom')=='Unknown' and tree.find('custom').get('key')=='value'
    assert b'<!--keep-->' in sidecar.read_bytes()
    assert tree.findtext('tag')=='手动标签' and tree.findtext('title')=='标题 & 特别版'


def test_series_exports_show_and_episode_including_season_zero(library,tmp_path):
    folder=tmp_path/'shows'/'Series'/'Season 0';folder.mkdir(parents=True)
    video=folder/'Series.S00E01.mp4';video.write_bytes(b'episode')
    library.import_folder(tmp_path/'shows','series',fast=True)
    work=library.query({'kinds':['series']})[0];identifier=work['id'];file=work['files'][0]
    library.edit_metadata(identifier,{'title':'整剧名称','tags':['剧集标签'],'episode_details':{str(file['id']):{'title':'特别篇','overview':'单集简介'}}},[])
    result=export_works(library,[identifier],images=False)
    assert result['written']==2 and not result['errors']
    show=nfo.read(folder.parent/'tvshow.nfo');episode=nfo.read(video.with_suffix('.nfo'))
    assert show['type']=='tvshow' and show['metadata']['title']=='整剧名称'
    assert episode['type']=='episodedetails' and episode['season']==0 and episode['episode']==1
    assert episode['metadata']['title']=='特别篇' and episode['metadata']['overview']=='单集简介'
    assert episode['showtitle']=='整剧名称'
    loaded=nfo.load(video,tmp_path/'shows','series',[])
    assert loaded['work']['metadata']['title']=='整剧名称'


def test_images_are_real_local_copies_referenced_by_nfo(library,tmp_path,qapp):
    video,identifier=media(library,tmp_path)
    cache=picture(library.directory/'cache'/'poster.png')
    actor=picture(library.directory/'cache'/'actor.png')
    metadata=json.loads(library.db.execute('SELECT metadata FROM works WHERE id=?',(identifier,)).fetchone()[0])
    metadata['actors'][0]['photo_cache']=str(actor)
    metadata.update(stills=['http://example.invalid/still'],stills_cache=[{'url':'http://example.invalid/still','path':str(cache)}])
    library.edit_metadata(identifier,metadata,[])
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(cache),identifier))
    result=export_works(library,[identifier])
    assert not result['errors'] and not result['warnings']
    root=ET.parse(video.with_suffix('.nfo'))
    poster=root.findtext('poster');portrait=root.findtext('actor/thumb')
    assert poster.endswith('.png') and (video.parent/poster).read_bytes()==cache.read_bytes()
    assert (video.parent/portrait).read_bytes()==actor.read_bytes()
    assert nfo.load(video,video.parent,'movie',[])['poster']==(video.parent/poster).resolve()
    assert nfo.read(video.with_suffix('.nfo'))['still_refs']


def test_bad_nfo_and_symlink_are_never_overwritten(library,tmp_path):
    video,identifier=media(library,tmp_path);sidecar=video.with_suffix('.nfo')
    before=b'<!DOCTYPE movie [<!ENTITY x "bad">]><movie><title>&x;</title></movie>';sidecar.write_bytes(before)
    result=export_works(library,[identifier],overwrite=True,images=False)
    assert result['errors'] and result['written']==0 and sidecar.read_bytes()==before
    sidecar.unlink();outside=tmp_path/'external.nfo';outside.write_text('<movie><title>Outside</title></movie>')
    try:sidecar.symlink_to(outside)
    except OSError:pytest.skip('Symlinks unavailable')
    result=export_works(library,[identifier],overwrite=True,images=False)
    assert result['errors'] and 'Outside' in outside.read_text()


def test_plan_does_not_write_and_publication_detects_concurrent_changes(library,tmp_path):
    video,identifier=media(library,tmp_path);sidecar=video.with_suffix('.nfo')
    preview=preview_export(library,[identifier],images=False)
    assert preview['paths']==[str(sidecar)] and not sidecar.exists()
    plan=plan_export(library,[identifier],images=False)
    sidecar.write_bytes(b'concurrent contents')
    with pytest.raises(ValueError,match='发生变化'):_publish(plan['entries'][0])
    assert sidecar.read_bytes()==b'concurrent contents'
    assert not list(video.parent.glob('.lumen-export-*'))


def test_cancel_before_replace_and_write_failure_preserve_original(library,tmp_path,monkeypatch):
    video,identifier=media(library,tmp_path);sidecar=video.with_suffix('.nfo');before=b'<movie><title>Before</title></movie>';sidecar.write_bytes(before)
    plan=plan_export(library,[identifier],overwrite=True,images=False)
    with pytest.raises(ImportCancelled):_publish(plan['entries'][0],cancelled=lambda:True)
    assert sidecar.read_bytes()==before and not list(video.parent.glob('.lumen-export-*'))
    def failed(*args):raise OSError('disk failure')
    monkeypatch.setattr('lumen.nfo_export.os.replace',failed)
    result=export_works(library,[identifier],overwrite=True,images=False)
    assert result['errors'] and sidecar.read_bytes()==before
    assert list(video.parent.glob('*.lumen-backup-*'))
    assert not list(video.parent.glob('.lumen-export-*'))


def test_external_id_table_completes_metadata_without_overriding_manual_ids(library,tmp_path):
    video,identifier=media(library,tmp_path)
    with library.db:
        library.db.executemany('INSERT INTO external_ids VALUES (?,?,?,?)',[
            ('movie','imdb','tt9999999',identifier),('movie','tvdb','456',identifier),
            ('movie','ambiguous','one',identifier),('movie','ambiguous','two',identifier)])
    result=export_works(library,[identifier],images=False)
    external=nfo.read(video.with_suffix('.nfo'))['metadata']['external_ids']
    assert external['imdb']=='tt1234567' and external['tvdb']=='456'
    assert 'ambiguous' not in external and result['warnings']
    raw=json.loads(library.db.execute('SELECT metadata FROM works WHERE id=?',(identifier,)).fetchone()[0])
    assert 'tvdb' not in raw['external_ids']


def test_same_stem_versions_share_sidecar_using_preferred_version(library,tmp_path):
    video,identifier=media(library,tmp_path)
    other=video.with_suffix('.mkv');other.write_bytes(b'other version')
    library.import_folder(video.parent,'movie',fast=True)
    work=library.work(identifier)
    alternative=next(file for file in work['files'] if file['path']==str(other))
    with library.db:library.db.execute('UPDATE files SET position=67 WHERE id=?',(alternative['id'],))
    library.set_setting('preferred-file:'+str(identifier),alternative['id'])
    result=export_works(library,[identifier],images=False)
    assert not result['errors'] and result['written']==1 and result['warnings']
    assert nfo.read(video.with_suffix('.nfo'))['position']==67
