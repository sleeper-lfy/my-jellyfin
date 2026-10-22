from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
import httpx
import pytest
from PySide6.QtGui import QImage, QColor
from lumen.plugins import Plugins, validate_metadata
from lumen.downloads import download_direct
from lumen.core import ImportCancelled
from lumen.artwork import still_paths
from lumen.server import LanServer
from lumen.ui import MainWindow


@pytest.fixture
def image_site(tmp_path):
    image=QImage(160,90,QImage.Format.Format_RGB32);image.fill(QColor('red'))
    path=tmp_path/'image.png';image.save(str(path));picture=path.read_bytes()
    counts={}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            counts[self.path]=counts.get(self.path,0)+1
            body=picture if self.path=='/image' else b'film-data'*300000
            self.send_response(200);self.send_header('Content-Type','image/png' if self.path=='/image' else 'application/octet-stream')
            self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',counts
    server.shutdown();server.server_close();thread.join()


def manager_for(library):
    manager=Plugins(library);manager.install(Path(__file__).parents[1]/'plugins/example')
    manager.configure('catalog-json',{'enabled':True});return manager


def test_plugin_stills_cache_gallery_and_authenticated_lan(qapp,library,image_site):
    base,counts=image_site;manager=manager_for(library)
    metadata={'id':'gallery','title':'Gallery Sample','url':base+'/detail','stills':[base+'/image',base+'/image'],
              'download_method':'magnet','download_url':[{'url':'magnet:?xt=urn:btih:'+'a'*40,'description':'sample magnet'},
                   {'url':base+'/file','method':'direct','description':'sample direct'}]}
    work_id=manager.merge('catalog-json',metadata)
    work=library.work(work_id);images=still_paths(work)
    assert len(images)==1 and Path(images[0]).is_file() and counts['/image']==1
    manager.merge('catalog-json',metadata,work_id)
    assert counts['/image']==1 and library.work(work_id)['metadata']['download_plugin']=='catalog-json'
    server=LanServer(library.directory,host='127.0.0.1',port=0);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            detail=client.get(f'/api/works/{work_id}').json()
            assert str(library.directory) not in json.dumps(detail)
            assert len(detail['stills'])==1 and len(detail['download_url'])==2
            assert client.get(detail['stills'][0]).content.startswith(b'\xff\xd8')
            assert client.get(detail['stills'][0],headers={'Authorization':''}).status_code==401
            assert client.get(f'/api/works/{work_id}/stills/99').status_code==404
    finally:server.stop()
    window=MainWindow(library.directory);window.open_details(work_id)
    assert window.detail_page.still_gallery.count()==1
    window.detail_page.show_still(window.detail_page.still_gallery.item(0))
    assert not window.detail_page.expanded_still.pixmap().isNull()
    window.close()


def test_direct_download_progress_cancel_and_no_partial_publish(library,image_site,tmp_path):
    base,_=image_site;manager_for(library)
    output=tmp_path/'movie.bin';reports=[]
    result=download_direct(library,'catalog-json',base+'/file',output,lambda *args:reports.append(args))
    assert output.read_bytes()==b'film-data'*300000 and result['bytes']==output.stat().st_size
    assert reports and reports[-1][0]==reports[-1][1]
    with pytest.raises(ValueError):download_direct(library,'catalog-json',base+'/file',output)
    cancelled=[False]
    def progress(*args):cancelled[0]=True
    target=tmp_path/'cancel.bin'
    with pytest.raises(ImportCancelled):download_direct(library,'catalog-json',base+'/file',target,progress,lambda:cancelled[0])
    assert not target.exists() and not list(tmp_path.glob('*.part'))
    with pytest.raises(ValueError):download_direct(library,'catalog-json','https://undeclared.example/file',target)
    assert library.db.execute("SELECT COUNT(*) FROM tasks WHERE kind='download' AND status='cancelled'").fetchone()[0]==1


def test_nfo_extrafanart_relocated_and_change_detected(qapp,library,video_factory):
    video=video_factory('Local.Gallery.mp4');extra=video.parent/'extrafanart';extra.mkdir()
    for name,color in [('one','red'),('two','blue')]:
        image=QImage(100,60,QImage.Format.Format_RGB32);image.fill(QColor(color));image.save(str(extra/(name+'.jpg')))
    video.with_suffix('.nfo').write_text('<movie><title>Local Gallery</title><art><fanart>Z:\\old\\extrafanart\\one.jpg</fanart></art></movie>')
    assert not library.import_folder(video.parent,'vr',fast=True)['errors']
    work=library.query()[0];assert len(still_paths(work))==2
    image=QImage(100,60,QImage.Format.Format_RGB32);image.fill(QColor('green'));image.save(str(extra/'three.jpg'))
    result=library.import_folder(video.parent,'vr',fast=True)
    assert result['nfo_updated']==1 and len(still_paths(library.work(work['id'])))==3


@pytest.mark.parametrize('extra',[{'stills':['file:///private.jpg']},{'stills':'https://example.org/a.jpg'},
    {'download_method':'exec'},{'download_method':'direct','download_url':[{'url':'magnet:?xt=x'}]},
    {'download_url':[{'url':'javascript:alert(1)','method':'direct'}]}])
def test_invalid_artwork_and_download_schema(extra):
    with pytest.raises(ValueError):validate_metadata({'id':'one','title':'Sample','url':'https://example.org',**extra})


def test_series_show_and_episode_metadata_and_stills(qapp,library,video_factory):
    video=video_factory('Journey 2.mp4');folder=video.parent
    image=QImage(100,60,QImage.Format.Format_RGB32);image.fill(QColor('blue'));image.save(str(folder/'episode-shot.jpg'))
    poster=QImage(60,100,QImage.Format.Format_RGB32);poster.fill(QColor('red'));poster.save(str(folder/'series-cover.jpg'))
    (folder/'tvshow.nfo').write_text('<tvshow><title>Entire Series</title><plot>Series overview</plot><season>-1</season><episode>-1</episode><art><poster>Z:\\old\\series-cover.jpg</poster></art></tvshow>')
    video.with_suffix('.nfo').write_text('<episodedetails><title>Episode Two</title><plot>Episode overview</plot><season>-1</season><episode>2</episode><thumb>episode-shot.jpg</thumb></episodedetails>')
    result=library.import_folder(folder,'series',fast=True)
    assert not result['errors'] and not result['warnings'],result
    work=library.query()[0];episode=work['files'][0]
    assert work['title']=='Entire Series' and work['metadata']['overview']=='Series overview'
    assert episode['title']=='Episode Two' and episode['overview']=='Episode overview'
    assert episode['episode']==2 and episode['season']==1 and len(episode['stills'])==1 and work['thumbnail']
    server=LanServer(library.directory,host='127.0.0.1',port=0);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            detail=client.get(f"/api/works/{work['id']}").json()
            assert detail['files'][0]['overview']=='Episode overview'
            assert client.get(detail['files'][0]['stills'][0]).content.startswith(b'\xff\xd8')
            assert str(folder) not in json.dumps(detail)
    finally:server.stop()
