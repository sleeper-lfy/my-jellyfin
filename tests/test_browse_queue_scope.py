import shutil
from urllib.parse import urlencode

import pytest

from lumen.core import Library
from test_core import add_work
from test_server import lan


def local_work(library, source, directory, title, **options):
    identifier = add_work(library, title, **options)
    path = directory / f'{identifier}.mp4'
    shutil.copyfile(source, path)
    with library.db:
        library.db.execute('UPDATE files SET path=?,root=? WHERE work_id=?', (str(path), str(directory), identifier))
    return identifier


def queue(client, path):
    return client.post('/api/queue/from-browse', json={'browse_path': path})


def test_saved_list_order_and_extra_filters_never_replace_saved_constraints(lan, library, tmp_path):
    client, _, source, _ = lan
    first = local_work(library, source, tmp_path, 'Alpha A', metadata={'tags': ['A']})
    second = local_work(library, source, tmp_path, 'Alpha Z', metadata={'tags': ['A', 'B']})
    outsider = local_work(library, source, tmp_path, 'Alpha outside', metadata={'tags': ['B']})
    beta = local_work(library, source, tmp_path, 'Beta outside', metadata={'tags': ['A']})
    for identifier in (first, second, outsider, beta): library.update_personal(identifier, favorite=True, watchlist=True)
    local_work(library, source, tmp_path, 'Alpha not saved', metadata={'tags': ['A']})
    saved = {'query': 'Alpha', 'favorite': True, 'watchlist': True, 'tags_all': ['A'], 'sort': 'title', 'descending': False}
    assert client.post('/api/lists', json={'name': 'Saved', 'filters': saved}).status_code == 200
    assert [work['id'] for work in client.get('/api/works?list=Saved').json()['items']] == [first, second]
    path = '/api/works?' + urlencode({'list': 'Saved', 'kind': '', 'q': '', 'favorite': 'false', 'watchlist': 'false', 'sort': 'title', 'direction': 'desc'})
    assert [work['id'] for work in client.get(path).json()['items']] == [second, first]
    assert set(queue(client, path).json()['ids']) == {first, second}
    assert [work['id'] for work in client.get(path+'&tag=B').json()['items']] == [second]
    assert queue(client, path+'&tag=B').json()['ids'] == [second]
    narrowed = '/api/works?list=Saved&q=Beta&sort=title&direction=desc'
    assert client.get(narrowed).json()['items'] == []
    assert queue(client, narrowed).json()['ids'] == []
    assert client.get('/api/works?list=missing').status_code == 404
    assert queue(client, '/api/works?list=missing').status_code == 404
    assert client.post('/api/lists', json={'name': 'Empty', 'filters': {'ids': []}}).status_code == 200
    assert queue(client, '/api/works?list=Empty').json()['ids'] == []


def test_scoped_queue_uses_entire_matching_collection_and_keeps_pc_queue(lan, library, tmp_path):
    client, _, source, _ = lan
    ids = [local_work(library, source, tmp_path, f'Progress {i}', metadata={'tags': ['Scoped']}) for i in range(36)]
    unwanted = local_work(library, source, tmp_path, 'Unwatched', metadata={'tags': ['Scoped']})
    offline = local_work(library, source, tmp_path, 'Offline progress', metadata={'tags': ['Scoped']})
    (tmp_path/f'{offline}.mp4').unlink()
    outside_root = local_work(library, source, tmp_path, 'Outside root', metadata={'tags': ['Scoped']})
    with library.db:
        library.db.executemany('UPDATE files SET position=20 WHERE work_id=?', [(identifier,) for identifier in [*ids, offline, outside_root]])
        library.db.execute('UPDATE files SET root=? WHERE work_id=?', (str(tmp_path/'different'), outside_root))
    library.edit_queue([unwanted], 'all'); before = library.setting('queue')
    path = '/api/works?tag=Scoped&watch_state=progress&offset=30&limit=1'
    visible = client.get(path).json()
    assert len(visible['items']) == 1 and visible['total'] == 38
    assert set(queue(client, path).json()['ids']) == set(ids)
    assert library.setting('queue') == before
    # Existing clients keep the old endpoint's behavior.
    assert unwanted in client.post('/api/queue', json={'tag': 'Scoped'}).json()['ids']
    assert queue(client, '/api/works?tag=Scoped&watch_state=completed').json()['ids'] == []


def test_recommendation_scope_is_shared_by_get_and_random_queue(lan, library, tmp_path, monkeypatch):
    client, _, source, _ = lan
    selected = local_work(library, source, tmp_path, 'Recommended', metadata={'tags': ['A']})
    excluded = local_work(library, source, tmp_path, 'Recommended filtered out', metadata={'tags': ['B']})
    local_work(library, source, tmp_path, 'Not recommended', metadata={'tags': ['A']})
    monkeypatch.setattr(Library, 'recommendations', lambda self: [self.work(excluded), self.work(selected)])
    path = '/api/recommendations?tag=A&offset=30&limit=1'
    assert client.get(path).json()['total'] == 1
    assert queue(client, path).json()['ids'] == [selected]


def test_discovery_hit_ids_keep_empty_results_and_exclude_nonlocal_records(lan, library, tmp_path):
    client, _, source, _ = lan
    first = local_work(library, source, tmp_path, 'Discovery local')
    second = local_work(library, source, tmp_path, 'Discovery outside hit list')
    metadata_only = add_work(library, 'Metadata only', local=False)
    with library.db:
        for identifier in (first, second, metadata_only):
            library.db.execute('INSERT INTO sources(work_id,plugin,site,source_id,url,updated) VALUES(?,?,?,?,?,?)',
                               (identifier, 'scope-provider', 'Scope', str(identifier), '', '2026-11-04'))
    path = f'/api/discover?ids={first},{metadata_only}&offset=20&limit=1&sort=title'
    assert client.get(path).json()['total'] == 2
    assert queue(client, path).json()['ids'] == [first]
    assert client.get('/api/discover?ids=').json()['items'] == []
    assert queue(client, '/api/discover?ids=').json()['ids'] == []


@pytest.mark.parametrize('path', ['https://example.org/api/works', '//example.org/api/works', '/api/tasks',
                                  '/api/works/1', '/api/works?unknown=1', '/api/works?kind=movie&kind=vr',
                                  '/api/works#fragment', '/api/works\n', '/api/works?ids=abc'])
def test_scoped_queue_rejects_unsupported_paths_without_falling_back(lan, path):
    client, _, _, _ = lan
    assert queue(client, path).status_code == 400
    assert client.post('/api/queue/from-browse', json={'browse_path': '/api/works'}, headers={'Authorization': ''}).status_code == 401
