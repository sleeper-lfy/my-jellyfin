"""Local HTTP contracts and real compatibility workers; no live-site claims."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import pytest
from lumen.core import ImportCancelled
from lumen.plugins import Plugins
from lumen.plugin_access import PluginHttpError,save_session,request_headers
from lumen.numbered_sources import resolve,check_source,SourceLookupError


@pytest.fixture
def site(library):
    seen=[];entered=threading.Event();release=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path,{key.title():value for key,value in self.headers.items()}))
            status=200;body=b'ok';headers={}
            if self.path.startswith('/challenge'):
                status=200 if self.path.endswith('200') else 403
                body=b'<html><title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/x"></script></html>'
                headers['cf-mitigated']='challenge'
            elif self.path=='/login':status=403;body=b'<html>Please log in</html>'
            elif self.path=='/denied':status=403;body=b'Forbidden: secret echo not for UI'
            elif self.path=='/rate':status=429
            elif self.path=='/redirect':status=302;headers['Location']=f'http://localhost:{self.server.server_port}/received'
            elif self.path=='/away':status=302;headers['Location']='http://unlisted.example/private'
            elif self.path=='/loop':status=302;headers['Location']='/loop'
            elif self.path=='/big':body=b'x'*4_000_001
            elif self.path=='/slow':entered.set();release.wait(6)
            elif self.path=='/session':
                if self.headers.get('Cookie')!='session=private-cookie' or self.headers.get('User-Agent')!='FixtureBrowser/1' or not self.headers.get('Referer'):status=403
                body=b'authorized' if status==200 else b'Forbidden'
            self.send_response(status);self.send_header('Content-Type','text/html')
            for key,value in headers.items():self.send_header(key,value)
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    manager=Plugins(library);manager.install(Path(__file__).parents[1]/'plugins/example')
    manager.configure('catalog-json',{'enabled':True,'base_url':base,'proxy':''})
    plugin=manager.installed()[0];plugin['domains']=['127.0.0.1','localhost']
    yield manager,plugin,base,seen,entered,release
    release.set();server.shutdown();server.server_close();thread.join(2)


def choose_transport(library,manager,plugin,transport,monkeypatch):
    save_session(library,plugin,{'transport':'browser' if transport=='browser' else 'standard'})
    if transport=='httpx':monkeypatch.setattr(manager,'_curl_binary',lambda:None)
    if transport=='httpx-cancel':
        monkeypatch.setattr(manager,'_curl_binary',lambda:None);manager.cancelled=lambda:False


@pytest.mark.parametrize('transport',['browser','curl','httpx','httpx-cancel'])
def test_real_requests_authentication_and_cross_origin_cookie_scope(library,site,monkeypatch,transport):
    manager,plugin,base,seen,_,_=site
    choose_transport(library,manager,plugin,transport,monkeypatch)
    with pytest.raises(PluginHttpError):manager.fetch(plugin,base+'/session')
    save_session(library,plugin,{'transport':'browser' if transport=='browser' else 'standard','cookie':'session=private-cookie','user_agent':'FixtureBrowser/1'})
    assert manager.fetch(plugin,base+'/session')[0]==b'authorized'
    assert 'private-cookie' not in json.dumps(manager.installed())
    assert manager.fetch(plugin,base+'/redirect')[0]==b'ok'
    assert seen[-2][1]['Cookie']=='session=private-cookie'
    assert 'Cookie' not in seen[-1][1] and seen[-1][1]['User-Agent']!='FixtureBrowser/1'
    assert not list(library.directory.glob('plugin-browser-*')) and not list(library.directory.glob('plugin-http-*'))


@pytest.mark.parametrize('transport',['browser','curl','httpx','httpx-cancel'])
def test_http_errors_distinguish_challenge_login_and_rate_limit(library,site,monkeypatch,transport):
    manager,plugin,base,*_=site;choose_transport(library,manager,plugin,transport,monkeypatch)
    for path,reason,retryable in [('/challenge','verification_required',False),('/challenge200','verification_required',False),('/login','login_required',False),('/denied','access_denied',False),('/rate','rate_limited',True)]:
        with pytest.raises(PluginHttpError) as error:manager.fetch(plugin,base+path)
        assert error.value.reason==reason and error.value.retryable==retryable
        assert 'secret' not in str(error.value)


def test_compatible_requests_retain_allowlist_redirect_and_size_guards(library,site,monkeypatch):
    manager,plugin,base,*_=site;choose_transport(library,manager,plugin,'browser',monkeypatch)
    with pytest.raises(ValueError,match='权限'):manager.fetch(plugin,'file:///etc/passwd')
    with pytest.raises(ValueError,match='权限'):manager.fetch(plugin,base+'/away')
    with pytest.raises(ValueError,match='重定向次数'):manager.fetch(plugin,base+'/loop')
    with pytest.raises(ValueError,match='响应大小'):manager.fetch(plugin,base+'/big')


def test_compatibility_worker_cancels_during_blocked_request(library,site,monkeypatch):
    manager,plugin,base,_,entered,release=site;choose_transport(library,manager,plugin,'browser',monkeypatch)
    cancel=threading.Event();manager.cancelled=cancel.is_set
    # Production workers own their SQLite connection; do the same here.
    def fetch():
        from lumen.core import Library
        worker=Library(library.directory)
        try:
            client=Plugins(worker);client.cancelled=cancel.is_set
            return client.fetch(plugin,base+'/slow')
        finally:worker.close()
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(fetch)
        try:
            assert entered.wait(3);start=time.monotonic();cancel.set()
            with pytest.raises(ImportCancelled):future.result(2)
            assert time.monotonic()-start<2
        finally:release.set()
    assert not list(library.directory.glob('plugin-browser-*'))


def test_native_compatibility_is_default_only_for_selected_providers(library,monkeypatch):
    manager=Plugins(library);called=[]
    monkeypatch.setattr(manager,'_fetch_browser',lambda *a:called.append('browser'))
    monkeypatch.setattr(manager,'_fetch_curl',lambda *a:called.append('standard'))
    monkeypatch.setattr(manager,'_curl_binary',lambda:'curl')
    plugin={'id':'javbus-films','domains':['example.org'],'config':{'base_url':'https://example.org','proxy':''}}
    manager.fetch(plugin,'https://example.org/movie');assert called==['browser']
    save_session(library,plugin,{'transport':'standard'})
    manager.fetch(plugin,'https://example.org/movie');assert called[-1]=='standard'
    manager.fetch({**plugin,'id':'tvmaze'},'https://example.org/movie');assert called[-1]=='standard'


def test_access_denial_falls_back_without_automatic_retry_or_false_empty_match(library,monkeypatch):
    manager=Plugins(library)
    for identifier in ('javbus-films','javdb-films'):
        manager.update_builtin_numbered_plugin(identifier);manager.configure(identifier,{'enabled':True})
    candidate={'id':'ABC-123','title':'ABC-123 Movie','kind':'movie','url':'https://javdb.com/v/abc','external_ids':{'product_code':'ABC-123'}}
    def run(self,identifier,operation,**kwargs):
        if identifier=='javbus-films':raise PluginHttpError(403,'verification_required','www.javbus.com','验证')
        return [candidate]
    monkeypatch.setattr(Plugins,'run',run)
    work={'title':'ABC-123','kind':'vr','year':None,'files':[]}
    result=resolve(library,work,'javbus-films',['javdb-films'])
    assert result['plugin']=='javdb-films' and result['attempts'][0]['http_status']==403
    with pytest.raises(SourceLookupError) as error:resolve(library,work,'javbus-films')
    assert not error.value.retryable
    health=check_source(library,'javbus-films','ABC-123')
    assert health['state']=='failed' and health['attempts'][0]['reason']=='verification_required'


def test_session_validation_origin_changes_and_uninstall(library,site):
    manager,plugin,base,*_=site
    for values in [{'cookie':'x\r\nX-Injected: true'},{'user_agent':'x\nCookie: leaked'},{'transport':'arbitrary-command'}]:
        with pytest.raises(ValueError):save_session(library,plugin,values)
    save_session(library,plugin,{'cookie':'session=private-cookie','user_agent':'FixtureBrowser/1'})
    for destination in (base.replace('http:','https:')+'/image','http://localhost:1234/image'):
        assert 'Cookie' not in request_headers(library,plugin,destination,{})
    changed={**plugin,'config':{**plugin['config'],'base_url':'http://localhost:1234'}}
    assert 'Cookie' not in request_headers(library,changed,'http://localhost:1234',{})
    manager.uninstall('catalog-json');assert library.setting('plugin-access:catalog-json')=={}


def test_access_ui_saves_separate_masked_session(qapp,library,site,tmp_path):
    from PySide6.QtWidgets import QLineEdit,QPushButton
    from lumen.ui import MainWindow
    from lumen.plugin_access_ui import show_plugin_access
    manager,plugin,base,*_=site
    window=MainWindow(library.directory)
    try:
        dialog=show_plugin_access(window,'catalog-json')
        field=dialog.findChild(QLineEdit,'siteCookie');assert field.echoMode()==QLineEdit.EchoMode.Password
        field.setText('session=private-cookie');dialog.findChild(QPushButton,'saveSiteAccess').click()
        assert window.library.setting('plugin-access:catalog-json')['cookie']=='session=private-cookie'
        assert 'private-cookie' not in json.dumps(Plugins(window.library).installed())
        dialog.close()
    finally:window.close()
