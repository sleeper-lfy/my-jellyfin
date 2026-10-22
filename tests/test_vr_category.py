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
