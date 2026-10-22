import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Thread
from pathlib import Path
import subprocess
import pytest
from lumen.plugins import Plugins
from test_core import add_work


@pytest.fixture
def catalog():
    records=[{'id':'one','title':'Real HTTP fixture','year':2024,'tags':['drama'],'actors':[{'name':'A','gender':'female'}], 'rating':7.2,
              'url':'https://example.org/film/one','site_added':'2025-01-01'}]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=json.dumps({'items':records}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(body)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}',records
    server.shutdown(); server.server_close(); thread.join()


@pytest.fixture
def manager(library,catalog):
    manager=Plugins(library)
    manager.install(Path(__file__).parents[1]/'plugins/example')
    manager.configure('catalog-json',{'enabled':True,'base_url':catalog[0]})
    return manager


def test_real_http_plugin_parse_merge_sources_and_locks(library,manager,catalog):
    result=manager.run('catalog-json','search',query='Real')
    assert result[0]['title']=='Real HTTP fixture'
    work_id=add_work(library,'Local title')
    library.edit_metadata(work_id,{'title':'Locked title','tags':['locked']},['title','tags'])
    manager.merge('catalog-json',result[0],work_id)
    w=library.work(work_id)
    assert w['title']=='Locked title' and w['metadata']['tags']==['locked']
    assert w['rating'] is None and w['sources'][0]['rating']==7.2
    manager.merge('catalog-json',result[0],work_id)
    assert len(library.work(work_id)['sources'])==1


def test_discovery_dedupe_across_sources(library,manager,tmp_path):
    first=manager.refresh('catalog-json')[0]
    assert library.work(first)['discovered']
    assert not library.work(first)['files']
    assert manager.refresh('catalog-json')==[first]
    folder=tmp_path/'second'; folder.mkdir()
    original=Path(__file__).parents[1]/'plugins/example'
    manifest=json.loads((original/'manifest.json').read_text())
    manifest['id']='second-source';manifest['name']='Second'
    (folder/'manifest.json').write_text(json.dumps(manifest))
    (folder/'plugin.js').write_text((original/'plugin.js').read_text())
    manager.install(folder)
    manager.configure('second-source',{'enabled':True,'base_url':manager.installed()[0]['config']['base_url']})
    assert manager.refresh('second-source')==[first]
    assert len(library.work(first)['sources'])==2
    assert library.query()==[]
    assert library.recommendations(True)[0]['id']==first


def test_disabled_permission_capability_and_other(library,manager):
    plugin=manager.installed()[0]
    with pytest.raises(ValueError): manager.fetch(plugin,'https://unlisted.example/test')
    with pytest.raises(ValueError): manager.fetch(plugin,'file:///etc/passwd')
    with pytest.raises(ValueError): manager.run('catalog-json','unsupported')
    other=add_work(library,'Video','other')
    record=manager.run('catalog-json','search',query='Video')[0]
    with pytest.raises(ValueError): manager.merge('catalog-json',record,other)
    manager.configure('catalog-json',{'enabled':False})
    with pytest.raises(ValueError): manager.run('catalog-json','discover')


def test_javascript_has_no_file_or_process_apis(manager):
    script=manager.root/'catalog-json/plugin.js'
    script.write_text('function inspect(x){return {require:typeof require,process:typeof process,fetch:typeof fetch,fs:typeof fs,qt:typeof Qt};}')
    result=manager.javascript('catalog-json','inspect',{})
    assert set(result.values())=={'undefined'}


def test_plugin_timeout_kills_worker(manager):
    script=manager.root/'catalog-json/plugin.js'
    script.write_text('function endless(x){while(true) {}}')
    with pytest.raises((subprocess.TimeoutExpired, RuntimeError)): manager.javascript('catalog-json','endless',{})


def test_plugin_output_validation_and_failure_log(manager,library):
    script=manager.root/'catalog-json/plugin.js'
    script.write_text('function buildRequest(x){return {url:x.config.base_url};} function parseResponse(x){return [{id:"x"}];}')
    with pytest.raises(ValueError): manager.run('catalog-json','search',query='x')
    assert library.db.execute('SELECT status FROM tasks ORDER BY updated DESC LIMIT 1').fetchone()[0]=='failed'


def test_proxy_is_shared_by_metadata_and_images(library,tmp_path,qapp):
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtCore import QBuffer,QByteArray,QIODevice
    image=QImage(24,36,QImage.Format.Format_RGB32);image.fill(QColor('blue'))
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);assert image.save(buffer,'PNG')
    picture=bytes(buffer.data())
    requests=[]
    class Proxy(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if self.path.startswith('http://images.invalid/'):
                data=picture;mime='image/png'
            else:
                data=json.dumps({'items':[{'id':'proxy','title':'Proxy fixture','year':2024,'url':'http://metadata.invalid/detail',
                     'poster':'http://images.invalid/poster.png','actors':[{'name':'Person','gender':'female','photo':'http://images.invalid/actor.png'}]}]}).encode();mime='application/json'
            self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(data)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        folder=tmp_path/'proxy-plugin';folder.mkdir()
        origin=Path(__file__).parents[1]/'plugins/example'
        manifest=json.loads((origin/'manifest.json').read_text())
        manifest['id']='proxy-site';manifest['domains']=['metadata.invalid','images.invalid']
        (folder/'manifest.json').write_text(json.dumps(manifest))
        (folder/'plugin.js').write_text((origin/'plugin.js').read_text())
        manager=Plugins(library);manager.install(folder)
        library.set_setting('proxy',f'http://127.0.0.1:{server.server_port}')
        manager.configure('proxy-site',{'enabled':True,'base_url':'http://metadata.invalid','proxy':'inherit'})
        work_id=manager.refresh('proxy-site')[0]
        work=library.work(work_id)
        assert Path(work['thumbnail']).is_file()
        assert Path(work['metadata']['actors'][0]['photo_cache']).is_file()
        assert requests==['http://metadata.invalid/catalog.json','http://images.invalid/poster.png','http://images.invalid/actor.png']
    finally:
        server.shutdown();server.server_close();thread.join()


def test_followup_request_uses_same_permission_boundary(manager,library):
    script=manager.root/'catalog-json/plugin.js'
    script.write_text('function buildRequest(x){return {url:x.config.base_url};} function parseResponse(x){return {records:[],followups:[{url:"https://not-allowed.example/private"}]};}')
    with pytest.raises(ValueError,match='权限'):manager.run('catalog-json','search',query='x')
    assert library.db.execute('SELECT status FROM tasks ORDER BY updated DESC LIMIT 1').fetchone()[0]=='failed'
