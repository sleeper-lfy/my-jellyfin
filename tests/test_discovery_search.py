import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from lumen.discovery_search import DiscoverySearchError, search_sites, search_providers
from lumen.plugins import Plugins
from lumen.core import ImportCancelled
from test_actor_plugins import portrait
from test_core import add_work
from test_server import lan


@pytest.fixture
def site(library, tmp_path, qapp):
    state = {'requests': [], 'fail': False, 'gate': Event(), 'entered': Event()}
    state['gate'].set()
    image = portrait(qapp)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'].append(self.path)
            if self.path.startswith('/search'):
                state['entered'].set(); state['gate'].wait(5)
                status = 500 if state['fail'] else 200
                body = json.dumps(state['items']).encode(); mime = 'application/json'
            else:
                status = 200; body = image; mime = 'image/png'
            self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    state['items'] = [{'id': 'one', 'title': 'Real online result', 'year': 2024, 'url': base+'/details/one',
                       'poster': base+'/poster.png', 'tags': ['Science fiction'], 'overview': 'Provider description',
                       'stills': [base+'/should-not-download.png'], 'actors': [{'name': 'Actor', 'photo': base+'/actor.png'}]}]
    folder = tmp_path / 'site-plugin'; folder.mkdir()
    manifest = {'api_version': 1, 'id': 'search-site', 'name': 'HTTP Search Site', 'version': '1.0',
                'capabilities': ['search', 'detail', 'discover'], 'search_filters': ['name', 'tag'],
                'domains': ['127.0.0.1'], 'base_url': base}
    (folder/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (folder/'plugin.js').write_text("function buildRequest(x){return {url:x.config.base_url+'/search?q='+encodeURIComponent(x.query||'')+'&tag='+encodeURIComponent(x.tag||'')};} function parseResponse(x){return JSON.parse(x.body);}", encoding='utf-8')
    manager = Plugins(library); manager.install(folder); manager.configure('search-site', {'enabled': True})
    state.update(base=base, manager=manager, folder=folder)
    yield state
    state['gate'].set(); server.shutdown(); server.server_close(); thread.join(timeout=5)


def wait_task(client, task_id, timeout=5):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        response = client.get('/api/discovery/search/'+task_id)
        assert response.status_code == 200
        state = response.json()
        if state['status'] not in {'queued', 'running'}: return state
        time.sleep(.02)
    raise AssertionError('Search task did not finish')


def test_real_site_search_preserves_terms_without_eager_image_downloads(library, site):
    result = search_sites(library, 'Real online', tag='Science fiction')
    assert result['count'] == result['added'] == result['matched'] == 1
    assert result['searched'] == ['search-site'] and result['errors'] == []
    assert len(site['requests']) == 1
    assert parse_qs(urlsplit(site['requests'][0]).query) == {'q': ['Real online'], 'tag': ['Science fiction']}
    work = library.work(result['ids'][0])
    assert work['thumbnail'] is None and work['metadata']['poster'].endswith('/poster.png')
    assert work['metadata']['stills'] and work['metadata']['actors'][0]['photo']
    assert not work['files'] and work['sources'][0]['plugin'] == 'search-site'


@pytest.mark.parametrize('association', ['source', 'identity', 'external_id'])
def test_site_hits_never_overwrite_local_metadata(library, site, association):
    record = site['items'][0]
    if association == 'identity':
        work_id = add_work(library, record['title'], metadata={'overview': 'User data', 'tags': ['Local tag']})
    else:
        work_id = add_work(library, 'Local custom title', metadata={'overview': 'User data', 'tags': ['Local tag']})
        with library.db:
            if association == 'source':
                library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                    (work_id, 'search-site', 'Existing source', 'one', record['url'], '2020-01-01', None, 8.0))
            else:
                library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)', ('movie', 'imdb', 'tt100', work_id))
                record['external_ids'] = {'imdb': 'tt100'}
    library.update_personal(work_id, favorite=True, rating=9)
    before = library.work(work_id)
    result = search_sites(library, 'Real online')
    assert result['ids'] == [work_id] and result['local_matches'] == 1 and result['added'] == 0
    assert library.work(work_id) == before
    assert len(site['requests']) == 1


def test_tag_only_unsupported_source_is_reported_not_discover_fallback(library, monkeypatch):
    manager = Plugins(library); manager.install(Path('plugins/tvmaze')); manager.configure('tvmaze', {'enabled': True})
    def forbidden(*args, **kwargs): raise AssertionError('Name-only provider must not be queried for a tag')
    monkeypatch.setattr(Plugins, 'run', forbidden)
    assert search_providers(library)[0] == {'id': 'tvmaze', 'name': 'TVmaze · 电视剧', 'search_filters': ['name'], 'supports_tags': False}
    with pytest.raises(DiscoverySearchError, match='不支持站点标签搜索') as error:
        search_sites(library, '', tag='Drama')
    assert error.value.result['ids'] == [] and error.value.result['errors'][0]['plugin'] == 'tvmaze'


def test_fans_same_name_is_separate_and_explicit_target_is_rejected_before_merge(library, site, monkeypatch):
    record = site['items'][0]
    fans_id = add_work(library, record['title'], kind='fans', metadata={'overview': 'Fans data'})
    original = library.work(fans_id)
    result = search_sites(library, 'Real')
    assert result['count'] == 1 and result['ids'] != [fans_id]
    assert library.work(result['ids'][0])['kind'] == 'movie' and library.work(fans_id) == original
    def forbidden(*args, **kwargs): raise AssertionError('No cross-work merge may run for a Fans target')
    monkeypatch.setattr(library, 'merge_works', forbidden)
    with pytest.raises(ValueError, match='Fans'):
        site['manager'].merge('search-site', record, fans_id)
    assert library.work(fans_id) == original


def test_source_previously_assigned_to_fans_cannot_refresh_it_as_a_movie(library, site):
    fans_id = add_work(library, 'Fans item', kind='fans', metadata={'overview': 'Fans data'})
    with library.db:
        library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
            (fans_id, 'search-site', 'Previous source', 'one', site['items'][0]['url'], '2020-01-01', None, None))
    before = library.work(fans_id)
    with pytest.raises(DiscoverySearchError, match='Fans'):
        search_sites(library, 'Real')
    assert library.work(fans_id) == before


def test_partial_source_support_keeps_results_and_each_source_error(library, site):
    manager = Plugins(library); manager.install(Path('plugins/tvmaze')); manager.configure('tvmaze', {'enabled': True})
    result = search_sites(library, '', tag='Science fiction')
    assert result['count'] == 1 and result['searched'] == ['search-site']
    assert result['errors'][0]['plugin'] == 'tvmaze' and '不支持' in result['errors'][0]['message']


def test_failure_is_not_zero_success_and_can_be_retried(library, site):
    site['fail'] = True
    with pytest.raises(DiscoverySearchError) as error: search_sites(library, 'Real')
    assert error.value.result['count'] == 0 and error.value.result['errors']
    assert library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0] == 0
    site['fail'] = False
    assert search_sites(library, 'Real')['count'] == 1
    assert search_sites(library, 'Real')['added'] == 0


def test_plugin_cancellation_stops_before_parser_and_is_not_a_failed_site(library, site, monkeypatch):
    manager = site['manager']; cancelled = [False]
    original_fetch = manager.fetch
    def fetch(*args, **kwargs):
        value = original_fetch(*args, **kwargs); cancelled[0] = True; return value
    monkeypatch.setattr(manager, 'fetch', fetch)
    original_javascript = manager.javascript
    def javascript(plugin_id, function, argument):
        assert function != 'parseResponse', 'A cancelled response must not run more JavaScript'
        assert 'cancelled' not in argument, 'Cancellation is a host callback, never a JS parameter'
        return original_javascript(plugin_id, function, argument)
    monkeypatch.setattr(manager, 'javascript', javascript)
    with pytest.raises(ImportCancelled):manager.run('search-site', 'search', query='Real', cancelled=lambda:cancelled[0])
    assert len(site['requests']) == 1
    assert library.db.execute('SELECT status FROM tasks ORDER BY updated DESC LIMIT 1').fetchone()[0] == 'cancelled'


def test_internet_archive_builds_real_title_and_subject_search(library):
    manager = Plugins(library); manager.install(Path('plugins/internet-archive'))
    plugin = manager.installed()[0]
    request = manager.javascript('internet-archive', 'buildRequest', {'operation': 'search', 'config': plugin['config'],
                                      'query': 'Night of the Living Dead', 'tag': 'Science fiction'})
    query = parse_qs(urlsplit(request['url']).query)['q'][0]
    assert 'mediatype:movies AND collection:feature_films' in query
    assert 'title:"Night of the Living Dead"' in query and 'subject:"Science fiction"' in query
    only_tag = manager.javascript('internet-archive', 'buildRequest', {'operation': 'search', 'config': plugin['config'],
                                      'query': '', 'tag': 'Science fiction'})
    assert 'title:' not in parse_qs(urlsplit(only_tag['url']).query)['q'][0]


def test_async_api_returns_immediately_and_authenticated_failures_are_retryable(site, lan):
    client, _, _, _ = lan
    assert client.get('/api/discovery/providers', headers={'Authorization': ''}).status_code == 401
    providers = client.get('/api/discovery/providers').json()['items']
    assert providers[0]['supports_tags'] and providers[0]['id'] == 'search-site'
    assert client.post('/api/discovery/search', json={'query': ''}).status_code == 400
    assert client.post('/api/discovery/search', json={'query': []}).status_code == 400
    site['gate'].clear()
    start = time.monotonic(); response = client.post('/api/discovery/search', json={'query': 'Real'})
    assert response.status_code == 202 and time.monotonic()-start<1
    task_id = response.json()['task_id']
    assert client.get('/api/info').status_code == 200
    assert client.get('/api/discovery/search/'+task_id).json()['status'] in {'queued', 'running'}
    site['gate'].set()
    state = wait_task(client, task_id)
    assert state['status'] == 'done' and state['result']['count'] == 1 and state['error'] is None
    assert client.get('/api/discovery/search/'+task_id, headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/discovery/search/'+'0'*32).status_code == 404
    site['fail'] = True
    failed = wait_task(client, client.post('/api/discovery/search', json={'query': 'Real'}).json()['task_id'])
    assert failed['status'] == 'failed' and failed['error'] and failed['result']['errors']
    site['fail'] = False
    assert wait_task(client, client.post('/api/discovery/search', json={'query': 'Real'}).json()['task_id'])['status'] == 'done'


def test_server_search_queue_is_bounded(site, lan):
    client, _, _, _ = lan
    site['gate'].clear()
    try:
        for _ in range(4): assert client.post('/api/discovery/search', json={'query': 'Real'}).status_code == 202
        response = client.post('/api/discovery/search', json={'query': 'Real'})
        assert response.status_code == 429 and '队列已满' in response.json()['error']
    finally: site['gate'].set()


def test_lan_lazily_loads_and_caches_only_requested_discovery_poster(library, site, lan):
    from PySide6.QtGui import QImage
    client, _, _, _ = lan
    result = search_sites(library, 'Real')
    work_id = result['ids'][0]
    detail = client.get(f'/api/works/{work_id}').json()
    assert detail['cover'] == f'/api/works/{work_id}/cover'
    assert site['requests'] == ['/search?q=Real&tag=']
    response = client.get(detail['cover'])
    assert response.status_code == 200
    image = QImage.fromData(response.content)
    assert not image.isNull() and image.width() <= 300 and image.height() <= 450
    assert library.work(work_id)['thumbnail']
    assert client.get(detail['cover']).status_code == 200
    assert site['requests'] == ['/search?q=Real&tag=', '/poster.png']


def test_lazy_cover_does_not_modify_a_work_imported_during_fetch(library, site, monkeypatch):
    from lumen.discovery_search import cache_discovery_cover
    from lumen import matching
    work_id = search_sites(library, 'Real')['ids'][0]
    original = matching.preview_cover
    def during_import(lib, plugin_id, record):
        assert not lib.db.in_transaction
        path = original(lib, plugin_id, record)
        with lib.db:
            lib.db.execute('INSERT INTO files(work_id,path,digest,root,duration) VALUES (?,?,?,?,?)', (work_id, '/media/new.mp4', 'imported', '/media', 100))
        lib.edit_metadata(work_id, {'overview': 'New local import'}, [])
        return path
    monkeypatch.setattr(matching, 'preview_cover', during_import)
    assert cache_discovery_cover(library, work_id)
    work = library.work(work_id)
    assert work['thumbnail'] is None and work['metadata']['overview'] == 'New local import' and work['files']
