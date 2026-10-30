import httpx
import pytest
from lumen.server import LanServer
from lumen.ui import MainWindow


def test_vr_import_nfo_and_lan_routing(library, video_factory):
    video=video_factory('VR.Sample.2025.mp4','green',2)
    video.with_suffix('.nfo').write_text('<movie><title>VR Sample</title><year>2025</year><rating>8.1</rating></movie>')
    result=library.import_folder(video.parent,'vr',fast=True)
    assert not result['errors'] and not result['warnings']
    work=library.query({'kinds':['vr']})[0]
    assert work['title']=='VR Sample' and work['kind']=='vr'
    server=LanServer(library.directory,host='127.0.0.1',port=0);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            data=client.get('/api/works?kind=vr').json()
            assert data['total']==1 and data['items'][0]['kind']=='vr'
            detail=client.get('/api/works/'+str(work['id'])).json()
            assert detail['kind']=='vr' and detail['files'][0]['stream']
            assert client.get('/api/works?kind=movie').json()['total']==0
    finally:
        server.stop()


def test_reclassification_preserves_files_and_personal_data(library, video_factory):
    library.import_folder(video_factory('Ordinary.mp4').parent,'movie',fast=True)
    work=library.query()[0];file=work['files'][0]
    library.update_personal(work['id'],favorite=True,rating=8)
    library.db.execute('UPDATE files SET position=1 WHERE id=?',(file['id'],));library.db.commit()
    library.set_movie_kind(work['id'],'vr')
    updated=library.work(work['id'])
    assert updated['kind']=='vr' and updated['favorite']==1 and updated['rating']==8
    assert updated['files'][0]['id']==file['id'] and updated['files'][0]['position']==1
    library.set_movie_kind(work['id'],'movie')
    assert library.work(work['id'])['kind']=='movie'
    with pytest.raises(ValueError):library.set_movie_kind(work['id'],'series')


def test_vr_navigation_and_filter(qapp,tmp_path):
    window=MainWindow(tmp_path/'vr-ui')
    window.navigate('vr')
    assert window.heading.text()=='VR电影'
    assert window.effective_filters()['kinds']==['vr']
    window.navigate('movie')
    assert window.effective_filters()['kinds']==['movie']
    window.close()


def test_vr_scrape_merges_discovered_movie_and_preserves_category(library):
    from test_core import add_work
    from test_gallery_downloads import manager_for
    from lumen.core import identity
    manager=manager_for(library)
    record={'id':'vr-match','title':'Shared film','year':2024,'kind':'movie',
            'url':'http://localhost/vr-match','external_ids':{'imdb':'tt-vr-match'}}
    discovered=manager.merge('catalog-json',record)
    library.update_personal(discovered,watchlist=True)
    target=add_work(library,'Shared film',kind='vr')
    library.update_personal(target,favorite=True,rating=9)
    file=library.work(target)['files'][0]
    with library.db:library.db.execute('UPDATE files SET position=123 WHERE id=?',(file['id'],))
    assert manager.merge('catalog-json',record,target)==target
    work=library.work(target)
    assert work['kind']=='vr' and work['favorite']==1 and work['rating']==9 and work['watchlist']==1
    assert work['files'][0]['id']==file['id'] and work['files'][0]['position']==123
    assert work['sources'][0]['source_id']=='vr-match'
    assert library.db.execute('SELECT id FROM works WHERE id=?',(discovered,)).fetchone() is None
    assert [tuple(row) for row in library.db.execute('SELECT kind,work_id FROM external_ids')]==[('vr',target)]
    assert library.db.execute('SELECT work_id FROM name_keys WHERE key=?',(identity('Shared film',2024,'movie'),)).fetchone() is None
    # Refreshes without an explicit work ID must also retain the VR category.
    assert manager.merge('catalog-json',{**record,'overview':'Refreshed'})==target
    assert library.work(target)['metadata']['overview']=='Refreshed'


def test_vr_scrape_never_merges_another_local_movie(library):
    from test_core import add_work
    from test_gallery_downloads import manager_for
    manager=manager_for(library)
    record={'id':'occupied','title':'Occupied film','url':'http://localhost/occupied'}
    source=add_work(library,'Occupied film')
    manager.merge('catalog-json',record,source)
    target=add_work(library,'VR target',kind='vr')
    with pytest.raises(ValueError,match='另一部本地媒体'):manager.merge('catalog-json',record,target)
    assert library.work(source)['kind']=='movie' and library.work(target)['kind']=='vr'


def test_vr_scrape_does_not_accept_series_candidates(library):
    from test_core import add_work
    from test_gallery_downloads import manager_for
    manager=manager_for(library);target=add_work(library,'VR target',kind='vr')
    with pytest.raises(ValueError,match='类型不匹配'):
        manager.merge('catalog-json',{'id':'series','title':'Series','kind':'series','url':'http://localhost/series'},target)
    assert library.work(target)['kind']=='vr' and not library.work(target)['sources']


def test_vr_scrape_conflict_rolls_back_discovery_absorption(library):
    from test_core import add_work
    from test_gallery_downloads import manager_for
    manager=manager_for(library)
    record={'id':'conflict','title':'Discovery','url':'http://localhost/conflict','external_ids':{'imdb':'source'}}
    discovered=manager.merge('catalog-json',record)
    target=add_work(library,'VR target',kind='vr')
    with library.db:library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)',('vr','imdb','target',target))
    with pytest.raises(ValueError,match='冲突'):manager.merge('catalog-json',record,target)
    assert library.work(discovered)['kind']=='movie' and library.work(discovered)['sources']
    assert library.work(target)['kind']=='vr' and not library.work(target)['sources']
    assert [tuple(row) for row in library.db.execute('SELECT kind FROM external_ids WHERE work_id=?',(discovered,))]==[('movie',)]


def test_vr_automatic_import_accepts_movie_scraper_result(qapp,tmp_path,monkeypatch):
    from test_core import add_work
    from test_gallery_downloads import manager_for
    from lumen.plugins import Plugins
    window=MainWindow(tmp_path/'auto-vr');manager_for(window.library)
    window.library.set_setting('partition:vr',{'plugin':'catalog-json'})
    target=add_work(window.library,'Auto VR',kind='vr');folder=tmp_path/'videos';folder.mkdir()
    with window.library.db:window.library.db.execute('UPDATE files SET path=?,root=? WHERE work_id=?',(str(folder/'Auto VR.mp4'),str(folder),target))
    monkeypatch.setattr(Plugins,'run',lambda *args,**kwargs:[{'id':'auto-vr','title':'Auto VR','year':2024,'kind':'movie','url':'http://localhost/auto-vr'}])
    monkeypatch.setattr(window,'run_job',lambda title,function:function(window.library,lambda *args:None))
    window.auto_scrape_import(str(folder),'vr')
    assert window.library.work(target)['kind']=='vr' and window.library.work(target)['sources'][0]['source_id']=='auto-vr'
    window.close()
