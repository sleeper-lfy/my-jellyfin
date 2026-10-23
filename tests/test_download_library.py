from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread,Event
import hashlib,json,time
import httpx
import pytest
from PySide6.QtGui import QImage,QColor
from lumen.core import Library,ImportCancelled
from lumen.downloads import (download_folder,default_download_root,set_download_folder,download_to_library,
                            launch_magnet,import_download_folder,video_filename)
from lumen.plugins import Plugins
from lumen.server import LanServer
from lumen.ui import MainWindow
from test_gallery_downloads import manager_for


@pytest.fixture
def media_site(video_factory):
    movie=video_factory('Unrelated.mp4','green').read_bytes()
    episode=video_factory('Show.S02E03.mp4','purple').read_bytes()
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            body=episode if self.path.startswith('/episode') else b'<html>denied</html>' if self.path=='/html' else movie
            self.send_response(200);self.send_header('Content-Length',str(len(body)))
            self.send_header('Content-Type','text/html' if self.path=='/html' else 'video/mp4')
            if self.path.startswith('/episode'):self.send_header('Content-Disposition',"attachment; filename*=UTF-8''Show.S02E03.mp4")
            self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',requests,movie,episode
    server.shutdown();server.server_close();thread.join()


def discovery(library,base,kind='movie',url='/Unrelated.mp4',id='sample',title='Chosen film'):
    manager=Plugins(library)
    if not manager.installed():manager_for(library)
    return manager.merge('catalog-json',{'id':id,'title':title,'kind':kind,'year':2024,'url':base+'/detail/'+id,
        'overview':'Chosen overview','tags':['Selected tag'],'actors':[{'name':'Selected actor'}],
        'download_method':'direct','download_url':[{'url':base+url,'description':'Real video'}]})


def test_default_roots_and_per_work_override_are_persistent(library,tmp_path):
    from test_core import add_work
    movie=add_work(library,'Chosen',local=False);series=add_work(library,'Show',kind='series',local=False)
    library.set_setting('downloads',{'movie':str(tmp_path/'Movies'),'series':str(tmp_path/'TV')})
    assert download_folder(library,movie)==tmp_path/'Movies'/'Chosen (2024)'
    assert download_folder(library,series)==tmp_path/'TV'/'Show (2024)'
    set_download_folder(library,movie,str(tmp_path/'Custom'))
    with pytest.raises(ValueError):set_download_folder(library,series,'relative/path')
    reopened=Library(library.directory)
    try:assert download_folder(reopened,movie)==tmp_path/'Custom'
    finally:reopened.close()
    set_download_folder(library,movie,'')
    assert download_folder(library,movie)==tmp_path/'Movies'/'Chosen (2024)'


def test_direct_video_download_imports_exact_work_and_writes_metadata(qapp,library,media_site,tmp_path):
    base,requests,body,_=media_site;work_id=discovery(library,base)
    library.set_setting('downloads',{'movie':str(tmp_path/'Movies')})
    image=QImage(80,120,QImage.Format.Format_RGB32);image.fill(QColor('red'))
    poster=library.directory/'cache'/'poster.jpg';image.save(str(poster))
    shot=library.directory/'cache'/'still.jpg';image.save(str(shot))
    with library.db:
        metadata=library.work(work_id)['metadata'];metadata['nfo_stills']=[str(shot)]
        library.db.execute('UPDATE works SET thumbnail=?,metadata=?,rating=9,favorite=1 WHERE id=?',(str(poster),json.dumps(metadata),work_id))
    progress=[]
    result=download_to_library(library,work_id,0,lambda *args:progress.append(args))
    work=library.work(work_id);folder=download_folder(library,work_id)
    assert len(work['files'])==1 and work['files'][0]['id']==result['file_id']
    assert Path(result['path']).read_bytes()==body
    assert work['files'][0]['digest']==hashlib.sha256(body).hexdigest()
    assert work['title']=='Chosen film' and work['metadata']['actors'][0]['name']=='Selected actor'
    assert work['rating']==9 and work['favorite']==1
    assert (folder/'movie.nfo').exists() and (folder/'poster.jpg').is_file() and (folder/'extrafanart'/'extrafanart-1.jpg').is_file()
    from lumen.nfo import read
    assert read(folder/'movie.nfo')['metadata']['title']=='Chosen film'
    assert progress and requests.count('/Unrelated.mp4')==1
    assert not list(folder.glob('*.part'))
    with pytest.raises(ValueError,match='已存在'):download_to_library(library,work_id,0)
    assert len(library.work(work_id)['files'])==1


def test_series_uses_content_disposition_and_series_info(qapp,library,media_site,tmp_path):
    base,_,_,body=media_site;work_id=discovery(library,base,kind='series',url='/episode?id=3',title='Whole show')
    library.set_setting('downloads',{'series':str(tmp_path/'TV')})
    result=download_to_library(library,work_id,0)
    file=library.work(work_id)['files'][0]
    assert file['season']==2 and file['episode']==3 and Path(file['path']).name=='Show.S02E03.mp4'
    assert Path(file['path']).read_bytes()==body and library.work(work_id)['title']=='Whole show'
    assert (download_folder(library,work_id)/'tvshow.nfo').is_file()
    assert Path(file['path']).with_suffix('.nfo').is_file()


def test_failed_or_cancelled_download_is_not_added(library,media_site,tmp_path):
    base,_,_,_=media_site;work_id=discovery(library,base,url='/html')
    set_download_folder(library,work_id,str(tmp_path/'Failed'))
    with pytest.raises(ValueError,match='没有返回视频'):download_to_library(library,work_id,0)
    assert not library.work(work_id)['files'] and not list((tmp_path/'Failed').glob('*.mp4'))
    with pytest.raises(ImportCancelled):download_to_library(library,work_id,0,cancelled=lambda:True)
    assert not library.work(work_id)['files'] and not list((tmp_path/'Failed').glob('*.part'))


def test_magnet_passes_directory_without_shell_and_import_is_explicit(qapp,library,tmp_path,video_factory,monkeypatch):
    import lumen.downloads as downloads
    work_id=discovery(library,'http://localhost')
    metadata=library.work(work_id)['metadata'];metadata['download_method']='magnet';metadata['download_url']=[{'url':'magnet:?xt=urn:btih:'+'a'*40}]
    with library.db:library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata),work_id))
    folder=tmp_path/'Magnet & literal $()';set_download_folder(library,work_id,str(folder))
    program=tmp_path/'qBittorrent.exe';program.write_bytes(b'test-placeholder')
    library.set_setting('downloads',{'magnet_client':'qbittorrent','magnet_executable':str(program)})
    commands=[];monkeypatch.setattr(downloads.subprocess,'Popen',lambda command,**kwargs:commands.append((command,kwargs)))
    result=launch_magnet(library,work_id,0)
    assert result['directory_sent'] and commands[0][0]==[str(program),'--save-path='+str(folder),'--skip-dialog=true',metadata['download_url'][0]['url']]
    assert commands[0][1]['shell'] is False and not library.work(work_id)['files']
    monkeypatch.undo()
    import shutil
    shutil.copy2(video_factory('Real.mp4'),folder/'Downloaded.mp4')
    result=import_download_folder(library,work_id)
    assert result['imported']==1 and not result['errors']
    assert import_download_folder(library,work_id)['duplicates']==1
    assert library.work(work_id)['title']=='Chosen film'


def test_authenticated_api_queues_download_and_refreshes_library(qapp,library,media_site,tmp_path):
    base,_,body,_=media_site;work_id=discovery(library,base)
    server=LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=0);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            route=f'/api/works/{work_id}'
            assert client.post(route+'/downloads',json={'index':0},headers={'Authorization':''}).status_code==401
            assert client.post(route+'/downloads',json={'index':99}).status_code==400
            folder=tmp_path/'Server save'
            assert client.post(route+'/download-directory',json={'directory':str(folder)}).json()['directory']==str(folder)
            assert client.get(route).json()['download_directory']==str(folder)
            response=client.post(route+'/downloads',json={'index':0});assert response.status_code==202
            task=response.json()['task_id'];deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                status=client.get('/api/downloads/'+task).json()
                if status['status'] in {'done','failed','partial'}:break
                time.sleep(.03)
            assert status['status']=='done',status
            assert (folder/'Unrelated.mp4').read_bytes()==body
            assert client.get(route).json()['file_count']==1
            assert client.get('/api/works').json()['total']==1
    finally:server.stop()


def test_opaque_series_download_remains_playable_without_invented_episode(qapp,library,media_site,tmp_path):
    base,_,_,_=media_site;work_id=discovery(library,base,kind='series',url='/Unrelated.mp4')
    set_download_folder(library,work_id,str(tmp_path/'Unknown episode'))
    download_to_library(library,work_id,0)
    file=library.work(work_id)['files'][0]
    assert file['season'] is None and file['episode'] is None
    window=MainWindow(library.directory);window.open_details(work_id,fetch=False)
    assert '待补充季集' in window.detail_page.files.item(0).text()
    window.close()


def test_filename_handles_endpoint_mime_and_rejects_archive():
    first=video_filename({'content-type':'video/x-matroska'},'https://example.org/download?id=1','Chosen')
    second=video_filename({'content-type':'video/x-matroska'},'https://example.org/download?id=2','Chosen')
    assert first.endswith('.mkv') and first!=second
    assert video_filename({'content-disposition':'attachment; filename="../../safe.mp4"'},'https://example.org/x','Chosen')=='safe.mp4'
    with pytest.raises(ValueError):video_filename({'content-type':'application/zip'},'https://example.org/archive.zip','Chosen')


def test_desktop_download_button_uses_saved_directory_without_extra_chooser(qapp,library,media_site,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    base,_,_,_=media_site;work_id=discovery(library,base)
    set_download_folder(library,work_id,str(tmp_path/'Click download'))
    def unexpected(*args,**kwargs):pytest.fail('A saved download directory must not prompt again')
    monkeypatch.setattr(QFileDialog,'getSaveFileName',unexpected);monkeypatch.setattr(QFileDialog,'getExistingDirectory',unexpected)
    window=MainWindow(library.directory);window.media_scheduler.stop();window.open_details(work_id,fetch=False)
    window.detail_page.resource_buttons[0].click()
    deadline=time.monotonic()+8
    while window.jobs and time.monotonic()<deadline:qapp.processEvents();time.sleep(.01)
    assert not window.jobs and window.detail_page.work_id==work_id
    assert len(window.detail_page.work['files'])==1 and '下载完成' in window.status.text()
    window.close()


def test_queued_download_keeps_selected_directory_and_deduplicates(qapp,library,media_site,tmp_path,monkeypatch):
    import lumen.downloads as downloads
    base,_,_,_=media_site
    first=discovery(library,base,id='first',title='First')
    second=discovery(library,base,id='second',title='Second',url='/episode?id=2')
    set_download_folder(library,first,str(tmp_path/'First'))
    set_download_folder(library,second,str(tmp_path/'Selected'))
    entered,proceed=Event(),Event();original=downloads.download_to_library
    def blocked(lib,work_id,*args,**kwargs):
        if work_id==first:entered.set();assert proceed.wait(5)
        return original(lib,work_id,*args,**kwargs)
    monkeypatch.setattr(downloads,'download_to_library',blocked)
    queue=downloads.DownloadQueue(library.directory)
    try:
        first_task=queue.submit(first,0);assert entered.wait(3)
        assert queue.submit(first,0)==first_task
        second_task=queue.submit(second,0)
        set_download_folder(library,second,str(tmp_path/'Changed later'))
        proceed.set();deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            states=[library.db.execute('SELECT status FROM tasks WHERE id=?',(task,)).fetchone()[0] for task in [first_task,second_task]]
            if states==['done','done']:break
            time.sleep(.03)
        assert states==['done','done']
        assert (tmp_path/'Selected'/'Show.S02E03.mp4').is_file()
        assert not (tmp_path/'Changed later').exists()
    finally:proceed.set();queue.stop()


def test_external_series_import_reads_episode_nfo_and_stills(qapp,library,tmp_path,video_factory):
    import shutil
    work_id=discovery(library,'http://localhost',kind='series',title='Canonical show')
    folder=tmp_path/'External series';folder.mkdir();set_download_folder(library,work_id,str(folder))
    video=folder/'Opaque.mp4';shutil.copy2(video_factory('Nfo episode.mp4'),video)
    shot=QImage(120,70,QImage.Format.Format_RGB32);shot.fill(QColor('blue'));shot.save(str(folder/'shot.jpg'))
    video.with_suffix('.nfo').write_text('<episodedetails><title>Actual episode title</title><season>3</season><episode>7</episode><plot>Episode story</plot><fanart>shot.jpg</fanart></episodedetails>')
    (folder/'tvshow.nfo').write_text('<tvshow><title>Do not rename selected show</title></tvshow>')
    result=import_download_folder(library,work_id)
    assert result['imported']==1 and not result['errors']
    work=library.work(work_id);file=work['files'][0]
    assert work['title']=='Canonical show' and file['season']==3 and file['episode']==7
    assert file['title']=='Actual episode title' and file['overview']=='Episode story' and file['stills']
