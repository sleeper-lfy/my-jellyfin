from pathlib import Path
import json
import shutil
import pytest
from lumen import nfo
from lumen.plugins import Plugins


def media(tmp_path, video_factory, name='Opaque.mp4', color='blue'):
    target=tmp_path/'media'/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(video_factory(name,color),target)
    return target


def test_movie_nfo_and_local_poster(library,tmp_path,video_factory,qapp):
    from PySide6.QtGui import QImage,QColor
    video=media(tmp_path,video_factory)
    sidecar=video.with_suffix('.NFO')
    sidecar.write_text('''<movie><title>本地影片</title><originaltitle>Original</originaltitle><year>2022</year>
    <plot>本地简介</plot><genre>剧情</genre><tag>收藏目录</tag><director>导演</director><studio>制作方</studio>
    <premiered>2022-01-02</premiered><uniqueid type="imdb">tt1234567</uniqueid>
    <ratings><rating name="imdb" max="100" default="true"><value>81</value></rating></ratings>
    <userrating>9</userrating><actor><name>演员</name><role>主角</role></actor>
    <resume><position>2</position></resume></movie>''',encoding='utf-8')
    image=QImage(100,150,QImage.Format.Format_RGB32);image.fill(QColor('red'));image.save(str(video.parent/'poster.png'))
    before=sidecar.read_bytes();result=library.import_folder(video.parent,'movie')
    assert result['imported']==1 and not result['warnings']
    work=library.work(library.query()[0]['id'])
    assert work['title']=='本地影片' and work['year']==2022 and work['rating']==9
    assert work['sources'][0]['rating']==8.1
    assert work['metadata']['actors'][0]['gender']=='unknown'
    assert work['metadata']['external_ids']=={'imdb':'tt1234567'}
    assert work['files'][0]['position']==2
    assert Path(work['thumbnail']).parent==library.directory/'cache'
    assert QImage(work['thumbnail']).pixelColor(10,10).red()>240
    assert sidecar.read_bytes()==before and video.exists()
    assert library.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0


def test_rescan_updates_metadata_preserves_personal_and_locks(library,tmp_path,video_factory):
    video=media(tmp_path,video_factory);library.import_folder(video.parent,'movie')
    work=library.query()[0];library.update_personal(work['id'],rating=7,favorite=True)
    library.edit_metadata(work['id'],{'overview':'手工锁定'},['overview'])
    library.db.execute('UPDATE files SET position=1');library.db.commit()
    video.with_suffix('.nfo').write_text('<movie><title>NFO 新标题</title><plot>不应覆盖</plot><userrating>2</userrating><watched>true</watched></movie>')
    result=library.import_folder(video.parent,'movie')
    assert result['nfo_updated']==1 and result['duplicates']==1
    work=library.work(work['id']);assert work['title']=='NFO 新标题'
    assert work['metadata']['overview']=='手工锁定'
    assert work['rating']==7 and work['favorite']==1
    assert work['files'][0]['position']==1 and work['files'][0]['completed']==0
    assert len(library.query())==1


def test_show_and_opaque_episode_nfo(library,tmp_path,video_factory):
    video=media(tmp_path,video_factory,'Show/Season 1/random.mp4')
    show=video.parent.parent
    (show/'tvshow.nfo').write_text('<tvshow><title>剧集总名</title><year>2020</year><plot>剧集简介</plot><uniqueid type="tvdb">123</uniqueid></tvshow>')
    video.with_suffix('.nfo').write_text('<episodedetails><title>第一集标题</title><season>0</season><episode>3</episode><plot>单集简介</plot><uniqueid type="tvdb">999</uniqueid><watched>true</watched></episodedetails>')
    result=library.import_folder(show,'series');assert result['imported']==1,result
    work=library.work(library.query()[0]['id']);file=work['files'][0]
    assert work['title']=='剧集总名' and work['metadata']['overview']=='剧集简介'
    assert file['season']==0 and file['episode']==3 and file['title']=='第一集标题'
    assert work['metadata']['external_ids']=={'tvdb':'123'}
    assert file['completed']==1
    assert len(library.query({'watched':'yes'}))==1
    assert library.query({'watched':'no'})==[]
    assert library.stats()['seconds']==0


@pytest.mark.parametrize('content', ['<movie><title>broken', '<!DOCTYPE movie [<!ENTITY x "expanded">]><movie><title>&x;</title></movie>', '<movie><year>bad</year></movie>'])
def test_bad_nfo_warns_and_keeps_video(library,tmp_path,video_factory,content):
    video=media(tmp_path,video_factory)
    video.with_suffix('.nfo').write_text(content)
    result=library.import_folder(video.parent,'movie')
    assert result['imported']==1 and result['warnings'] and not result['errors']
    assert library.query()[0]['title']=='Opaque'


def test_utf16_entities_blocked_and_normal_utf16_read(tmp_path):
    path=tmp_path/'movie.nfo'
    path.write_bytes('<movie><title>中文</title></movie>'.encode('utf-16'))
    assert nfo.read(path)['metadata']['title']=='中文'
    path.write_bytes('<!DOCTYPE movie [<!ENTITY x "expanded">]><movie><title>&x;</title></movie>'.encode('utf-16'))
    with pytest.raises(ValueError,match='DTD'):nfo.read(path)


def test_movie_nfo_fallback_and_poster_escape(library,tmp_path,video_factory):
    video=media(tmp_path,video_factory)
    (video.parent/'movie.nfo').write_text('<movie><title>Fallback</title><thumb>../../outside.jpg</thumb></movie>')
    (tmp_path/'outside.jpg').write_bytes(b'not read')
    data=nfo.load(video,video.parent,'movie',[])
    assert data['poster'] is None
    assert library.import_folder(video.parent,'movie')['imported']==1
    assert library.query()[0]['title']=='Fallback'


def test_external_id_conflict_rolls_back(library,tmp_path,video_factory):
    first=media(tmp_path,video_factory,'First.mp4')
    first.with_suffix('.nfo').write_text('<movie><title>同名</title><uniqueid type="imdb">tt1</uniqueid></movie>')
    library.import_folder(first.parent,'movie')
    second=media(tmp_path,video_factory,'Second.mp4','green')
    second.with_suffix('.nfo').write_text('<movie><title>同名</title><uniqueid type="imdb">tt2</uniqueid></movie>')
    result=library.import_folder(first.parent,'movie')
    assert result['errors'] and len(library.query())==1
    assert len(library.query()[0]['files'])==1 and second.exists()


def test_online_metadata_only_fills_missing_fields(library,tmp_path,video_factory):
    video=media(tmp_path,video_factory)
    video.with_suffix('.nfo').write_text('<movie><title>本地标题</title><plot>本地简介</plot></movie>')
    library.import_folder(video.parent,'movie');work=library.query()[0]
    plugins=Plugins(library);manifest=plugins.install(Path('plugins/example'))
    plugins.merge(manifest['id'],{'id':'1','title':'网站标题','kind':'movie','url':'https://example.org/1','overview':'网站简介','directors':['新增导演']},work['id'])
    updated=library.work(work['id'])
    assert updated['title']=='本地标题' and updated['metadata']['overview']=='本地简介'
    assert updated['metadata']['directors']==['新增导演']


def test_episodes_share_show_and_keep_individual_titles(library,tmp_path,video_factory):
    first=media(tmp_path,video_factory,'Show/Season 1/one.mp4')
    second=media(tmp_path,video_factory,'Show/Season 1/two.mp4','yellow')
    (first.parent.parent/'tvshow.nfo').write_text('<tvshow><title>A Show</title><uniqueid type="tvdb">555</uniqueid></tvshow>')
    for number,video in enumerate([first,second],1):
        video.with_suffix('.nfo').write_text(f'<episodedetails><title>Episode {number}</title><season>1</season><episode>{number}</episode></episodedetails>')
    result=library.import_folder(first.parent.parent,'series')
    assert result['imported']==2,result
    assert len(library.query())==1
    work=library.work(library.query()[0]['id'])
    assert [f['title'] for f in work['files']]==['Episode 1','Episode 2']
    assert len(work['sources'])==1


def test_nfo_size_bound_and_no_network_poster(tmp_path,video_factory):
    video=media(tmp_path,video_factory)
    path=video.with_suffix('.nfo')
    path.write_text('<movie><title>A</title><thumb>https://example.org/poster.jpg</thumb></movie>')
    assert nfo.load(video,video.parent,'movie',[])['poster'] is None
    path.write_bytes(b' '*(nfo.MAX_NFO+1))
    with pytest.raises(ValueError,match='2 MB'):nfo.read(path)


def test_local_poster_is_not_replaced_by_online_plugin(library,tmp_path,video_factory,monkeypatch,qapp):
    from PySide6.QtGui import QImage,QColor
    video=media(tmp_path,video_factory)
    video.with_suffix('.nfo').write_text('<movie><title>Local</title></movie>')
    picture=QImage(10,10,QImage.Format.Format_RGB32);picture.fill(QColor('blue'));picture.save(str(video.parent/'poster.jpg'))
    library.import_folder(video.parent,'movie');work=library.query()[0]
    plugins=Plugins(library);manifest=plugins.install(Path('plugins/example'))
    def forbidden(*args,**kwargs):pytest.fail('Local NFO artwork must not trigger a network fetch')
    monkeypatch.setattr(plugins,'fetch',forbidden)
    plugins.merge(manifest['id'],{'id':'poster-test','title':'Local','url':'https://example.org/1','poster':'https://example.org/p.jpg'},work['id'])
    assert library.work(work['id'])['thumbnail']==work['thumbnail']


def test_nfo_original_title_matches_online_source(library,tmp_path,video_factory):
    video=media(tmp_path,video_factory)
    video.with_suffix('.nfo').write_text('<movie><title>本地标题</title><originaltitle>Original Title</originaltitle><year>2024</year></movie>')
    library.import_folder(video.parent,'movie');work=library.query()[0]
    plugins=Plugins(library);manifest=plugins.install(Path('plugins/example'))
    matched=plugins.merge(manifest['id'],{'id':'alias-test','title':'Original Title','year':2024,'url':'https://example.org/alias'})
    assert matched==work['id'] and len(library.query())==1
    assert library.work(matched)['title']=='本地标题'
