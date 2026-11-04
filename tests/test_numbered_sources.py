"""Offline fixtures model known page elements; no claims of live site validation."""
import copy
import json
from pathlib import Path
import pytest
from lumen.plugins import Plugins,validate_metadata
from lumen.numbered_sources import resolve,SourceLookupError,check_source
from lumen.ingestion import choose,enqueue,process_pending
from test_ingestion import imported

FIXTURES=Path(__file__).parent/'fixtures/numbered_sources'


@pytest.mark.parametrize('site',['javbus','javdb'])
def test_numbered_plugin_search_detail_and_no_downloads(library,site):
    manager=Plugins(library);manifest=manager.update_builtin_numbered_plugin(site+'-films')
    assert not library.setting('plugin:'+site+'-films')['enabled']
    manager.configure(site+'-films',{'enabled':True})
    config=library.setting('plugin:'+site+'-films')
    req=manager.javascript(site+'-films','buildRequest',{'operation':'search','query':'abc_123','config':config})
    assert 'ABC-123' in req['url']
    records=manager.javascript(site+'-films','parseResponse',{'operation':'search','url':req['url'],'body':(FIXTURES/(site+'-search.html')).read_text(),'config':config})
    candidate=choose({'kind':'vr','title':'ABC-123','files':[],'year':None},records)
    details=manager.javascript(site+'-films','parseResponse',{'operation':'detail','url':candidate['url'],'body':(FIXTURES/(site+'-detail.html')).read_text(),'config':config})
    record=details[0];validate_metadata(record)
    assert record['id']==candidate['id'] and record['external_ids']['product_code']=='ABC-123'
    assert record['year']==2024 and record['tags']==['剧情'] and record['actors'][0]['name']=='示例演员'
    assert record['poster'].startswith('https://') and len(record['stills'])==1 and record['overview']
    assert 'download_url' not in record and 'download_method' not in record
    assert 'magnet:' not in json.dumps(record)
    manager.configure(site+'-films',{'proxy':'http://localhost:1234','priority':7})
    manager.update_builtin_numbered_plugin(site+'-films')
    assert library.setting('plugin:'+site+'-films')['proxy']=='http://localhost:1234'
    with pytest.raises(ValueError):manager.fetch(manager.installed()[0],'https://unlisted.example.org/private')


@pytest.mark.parametrize('body',['<html><title>Just a moment</title>__cf_chl</html>','<html><div>unexpected markup</div></html>'])
def test_blocked_or_changed_page_is_not_silent_empty_success(library,body):
    manager=Plugins(library);manager.update_builtin_numbered_plugin('javdb-films')
    with pytest.raises(RuntimeError):
        manager.javascript('javdb-films','parseResponse',{'operation':'search','body':body,'config':{}})


def providers(library):
    manager=Plugins(library)
    for site in ('javbus','javdb'):
        manager.update_builtin_numbered_plugin(site+'-films');manager.configure(site+'-films',{'enabled':True})
    return manager


def candidate(identifier='ABC-123'):
    return {'id':identifier,'title':'ABC-123 Example','kind':'movie','url':'https://www.javbus.com/ABC-123','external_ids':{'product_code':'ABC-123'}}


def test_fallback_on_network_and_no_match_reads_detail_and_preserves_vr(library,tmp_path,monkeypatch):
    providers(library);path,work=imported(library,tmp_path);calls=[]
    def run(self,plugin,operation,**kwargs):
        calls.append((plugin,operation))
        if plugin=='javbus-films':raise OSError('source unavailable')
        value=candidate('MNOP12');value['url']='https://javdb.com/v/MNOP12'
        if operation=='detail':value['overview']='Full detail'
        return [value]
    monkeypatch.setattr(Plugins,'run',run)
    library.set_setting('numbered_fallbacks:vr',['javdb-films'])
    enqueue(library,work,'javbus-films','')
    assert process_pending(library)['completed']==1
    current=library.work(work['id']);assert current['kind']=='vr' and current['metadata']['overview']=='Full detail'
    assert current['sources'][0]['plugin']=='javdb-films'
    assert calls==[('javbus-films','search'),('javdb-films','search'),('javdb-films','detail')]


def test_ambiguity_never_selects_first_and_keeps_candidate_source(library,tmp_path,monkeypatch):
    providers(library);path,work=imported(library,tmp_path)
    def run(self,plugin,operation,**kwargs):
        if plugin=='javbus-films':return [candidate('one'),candidate('two')]
        return []
    monkeypatch.setattr(Plugins,'run',run)
    with pytest.raises(SourceLookupError) as info:resolve(library,work,'javbus-films',['javdb-films'])
    assert not info.value.retryable and len(info.value.candidates)==2 and info.value.plugin=='javbus-films'
    assert path.is_file() and not library.work(work['id'])['sources']


def test_health_probe_does_not_create_media_and_reports_no_match(library,monkeypatch):
    providers(library)
    monkeypatch.setattr(Plugins,'run',lambda *args,**kwargs:[])
    result=check_source(library,'javbus-films','ABC-123')
    assert result['state']=='no_unique_match' and not result['matched']
    assert library.setting('source-health:javbus-films')['state']=='no_unique_match'
    assert not library.query({'local':False})


def test_detail_cannot_switch_number_even_when_provider_id_matches(library,tmp_path,monkeypatch):
    providers(library);path,work=imported(library,tmp_path)
    def run(self,plugin,operation,**kwargs):
        value=candidate();
        if operation=='detail':value['external_ids']['product_code']='ABC-124'
        return [value]
    monkeypatch.setattr(Plugins,'run',run)
    with pytest.raises(SourceLookupError):resolve(library,work,'javbus-films',[])
    assert not library.work(work['id'])['sources']


def test_source_window_routes_to_single_defaults_editor_without_changing_rules(qapp,tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    from PySide6.QtWidgets import QPushButton
    from lumen.ui import MainWindow
    from lumen.numbered_sources_ui import show_numbered_providers
    window=MainWindow(tmp_path/'sources-ui');opened=[]
    monkeypatch.setitem(sys.modules,'lumen.media_management_ui',SimpleNamespace(show_media_management=lambda owner,section:opened.append((owner,section))))
    try:
        providers(window.library)
        original={'plugin':'javbus-films','destination':'D:/Movies','other':'keep'}
        window.library.set_setting('partition:movie',original)
        window.library.set_setting('numbered_fallbacks:movie',['javdb-films'])
        dialog=show_numbered_providers(window)
        assert show_numbered_providers(window) is dialog
        assert not any('保存此分类' in button.text() for button in dialog.findChildren(QPushButton))
        dialog.findChild(QPushButton,'configureIngestionDefaults').click()
        assert opened==[(window,'sources')]
        assert window.library.setting('partition:movie')==original
        assert window.library.setting('numbered_fallbacks:movie')==['javdb-films']
    finally:window.close()
