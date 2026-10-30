"""Independent portrait records, provider adapters and safe library application."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from lumen.plugins import Plugins, validate_actor
from test_core import add_work
from test_server import lan


def portrait(qapp, color='blue'):
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage, QColor
    image = QImage(40, 60, QImage.Format.Format_RGB32); image.fill(QColor(color))
    buffer = QBuffer(); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'PNG')
    return bytes(buffer.data())


def provider(library, plugin_id='tvmaze'):
    manager = Plugins(library)
    manager.install(Path(__file__).parents[1] / 'plugins' / plugin_id)
    manager.configure(plugin_id, {'enabled': True})
    return manager


def credit(library, title, name='Local actor', *, locked=False, photo=None):
    work_id = add_work(library, title)
    actor = {'name': name, 'gender': 'female', 'aliases': ['Local alias'] if name == 'Local actor' else []}
    if photo: actor['photo_cache'] = str(photo)
    library.edit_metadata(work_id, {'actors': [actor], 'overview': 'Keep this'}, ['actors'] if locked else [])
    return work_id


def candidate():
    return {'id': 'tvmaze:9', 'name': 'Provider spelling', 'gender': 'female', 'aliases': [],
            'url': 'https://www.tvmaze.com/people/9/person', 'photo': 'https://static.tvmaze.com/person.jpg'}


JAVBUS_SEARCH = '''<html><body>
<div class="item"><a class="movie-box" href="/star/abc123"><div class="photo-frame">
<img src="/pics/actress/abc123_a.jpg" title="Sample Performer"></div>
<div class="photo-info"><span>Sample Performer</span></div></a></div>
<div class="item"><a class="movie-box" href="https://www.javbus.com/star/def456">
<img src="https://www.javbus.com/pics/actress/def456_a.jpg" alt="Second Performer"></a></div>
<a href="/star/abc123"><img src="/pics/actress/abc123_a.jpg" alt="Duplicate"></a>
</body></html>'''

JAVBUS_TEXT_ONLY = '''<html><body>
<a href="/star/ghi789">Third Performer</a>
</body></html>'''

JAVBUS_STAR = '''<html><body>
<div class="avatar-box"><img src="/pics/actress/ghi789_a.jpg" title="Third Performer"></div>
</body></html>'''

JAVBUS_REDIRECTED_STAR = '''<html><head>
<link rel="canonical" href="https://www.javbus.com/star/xyz789">
<title>Sample Performer - JavBus</title></head><body>
<div class="avatar-box"><img src="/pics/actress/xyz789_a.jpg" title="Sample Performer"></div>
</body></html>'''

JAVDB_SEARCH = '''<html><body>
<div id="actors" class="actors">
  <div class="box actor-box">
    <a href="/actors/G9P5" title="麻里梨夏, 涼野しずく, 成海うるみ">
      <figure class="image"><img class="avatar" src="https://c0.jdbstatic.com/avatars/g9/G9P5.jpg" /></figure>
      <strong>麻里梨夏</strong>
    </a>
  </div>
  <div class="box actor-box">
    <a href="/actors/g0qVA" title="麻里梨夏">
      <figure class="image"><img class="avatar" src="https://c0.jdbstatic.com/images/actor_unknow.jpg" /></figure>
      <strong>麻里梨夏</strong>
    </a>
  </div>
</div>
</body></html>'''


def test_javbus_actor_parses_redirected_single_star_page(library, monkeypatch):
    manager = provider(library, 'javbus-actors')
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: (JAVBUS_REDIRECTED_STAR.encode('utf-8'), 'text/html'))
    rows = manager.run('javbus-actors', 'actors', query='Sample Performer')
    assert len(rows) == 1
    assert rows[0]['id'] == 'javbus:xyz789'
    assert rows[0]['name'] == 'Sample Performer'
    assert rows[0]['url'] == 'https://www.javbus.com/star/xyz789'
    assert rows[0]['photo'] == 'https://www.javbus.com/pics/actress/xyz789_a.jpg'


def test_javbus_actor_search_parses_portraits_and_ignores_duplicates(library, monkeypatch):
    manager = provider(library, 'javbus-actors')
    calls = []

    def fetch(plugin, url, image=False):
        calls.append(url)
        return JAVBUS_SEARCH.encode('utf-8'), 'text/html'

    monkeypatch.setattr(manager, 'fetch', fetch)
    rows = manager.run('javbus-actors', 'actors', query='Sample Performer')
    assert len(calls) == 1
    assert urlsplit(calls[0]).path == '/searchstar/Sample%20Performer'
    assert [row['id'] for row in rows] == ['javbus:abc123', 'javbus:def456']
    assert rows[0]['name'] == 'Sample Performer'
    assert rows[0]['gender'] == 'female'
    assert rows[0]['url'] == 'https://www.javbus.com/star/abc123'
    assert rows[0]['photo'] == 'https://www.javbus.com/pics/actress/abc123_a.jpg'
    assert rows[0]['photo_page'] == rows[0]['url']
    assert 'title' not in rows[0]
    assert library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0] == 0


def test_javbus_actor_follows_star_page_when_search_has_no_portrait(library, monkeypatch):
    manager = provider(library, 'javbus-actors')
    calls = []

    def fetch(plugin, url, image=False):
        calls.append(url)
        if '/searchstar/' in url:
            return JAVBUS_TEXT_ONLY.encode('utf-8'), 'text/html'
        return JAVBUS_STAR.encode('utf-8'), 'text/html'

    monkeypatch.setattr(manager, 'fetch', fetch)
    rows = manager.run('javbus-actors', 'actors', query='Third')
    assert calls == ['https://www.javbus.com/searchstar/Third', 'https://www.javbus.com/star/ghi789']
    assert len(rows) == 1 and rows[0]['id'] == 'javbus:ghi789'
    assert rows[0]['name'] == 'Third Performer'
    assert rows[0]['photo'] == 'https://www.javbus.com/pics/actress/ghi789_a.jpg'


def test_javbus_actor_does_not_fabricate_without_results(library, monkeypatch):
    manager = provider(library, 'javbus-actors')
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: ('<div>not found</div>'.encode('utf-8'), 'text/html'))
    assert manager.run('javbus-actors', 'actors', query='Nobody') == []


def test_javbus_actor_reports_browser_verification_page(library, monkeypatch):
    manager = provider(library, 'javbus-actors')
    page = ('<html><head><title>Verification</title></head><body>'
            '<script>location="/doc/driver-verify?referer=x"</script></body></html>')
    calls = []

    def fetch(plugin, url, image=False):
        calls.append(url)
        return page.encode('utf-8'), 'text/html'

    monkeypatch.setattr(manager, 'fetch', fetch)
    with pytest.raises(RuntimeError, match='浏览器验证'):
        manager.run('javbus-actors', 'actors', query='Sample')
    assert calls[1].startswith('https://r.jina.ai/https://www.javbus.com/searchstar/')


READER_SEARCH = '''Title: Search Result
URL Source: https://www.javbus.com/searchstar/Sample

Markdown Content:

[Sample Performer](https://www.javbus.com/star/abc123)

![Sample Performer](https://www.javbus.com/pics/actress/abc123_a.jpg)

[Second Performer](https://www.javbus.com/star/def456)

![Second Performer](https://www.javbus.com/pics/actress/def456_a.jpg)
'''

READER_LINKS_ONLY = '''Title: Search Result
URL Source: https://www.javbus.com/searchstar/Sample

Markdown Content:

[Third Performer](https://www.javbus.com/star/ghi789)
'''

READER_STAR = '''Title: Third Performer
URL Source: https://www.javbus.com/star/ghi789

Markdown Content:

![Third Performer](https://www.javbus.com/pics/actress/ghi789_a.jpg)
'''


def test_javbus_actor_reader_fallback_pairs_images_with_links(library, monkeypatch):
    manager = provider(library, 'javbus-actors')
    calls = []

    def fetch_verify(plugin, url, image=False):
        calls.append(url)
        if '/searchstar/' in url and 'r.jina.ai' not in url:
            return ('<div>driver-verify</div>'.encode('utf-8'), 'text/html')
        return READER_SEARCH.encode('utf-8'), 'text/plain'

    monkeypatch.setattr(manager, 'fetch', fetch_verify)
    rows = manager.run('javbus-actors', 'actors', query='Sample')
    assert calls[0].startswith('https://www.javbus.com/searchstar/')
    assert calls[1].startswith('https://r.jina.ai/https://www.javbus.com/searchstar/')
    assert [row['id'] for row in rows] == ['javbus:abc123', 'javbus:def456']
    assert rows[0]['photo'] == 'https://www.javbus.com/pics/actress/abc123_a.jpg'
    assert rows[0]['name'] == 'Sample Performer'


def test_javbus_actor_reader_follows_star_page_for_portrait(library, monkeypatch):
    manager = provider(library, 'javbus-actors')
    calls = []

    def fetch(plugin, url, image=False):
        calls.append(url)
        if 'r.jina.ai' not in url:
            return ('<html>driver-verify</html>'.encode('utf-8'), 'text/html')
        if '/searchstar/' in url:
            return READER_LINKS_ONLY.encode('utf-8'), 'text/plain'
        return READER_STAR.encode('utf-8'), 'text/plain'

    monkeypatch.setattr(manager, 'fetch', fetch)
    rows = manager.run('javbus-actors', 'actors', query='Third')
    assert len(calls) == 3
    assert calls[1] == 'https://r.jina.ai/https://www.javbus.com/searchstar/Third'
    assert calls[2] == 'https://r.jina.ai/https://www.javbus.com/star/ghi789'
    assert len(rows) == 1 and rows[0]['id'] == 'javbus:ghi789'
    assert rows[0]['name'] == 'Third Performer'
    assert rows[0]['photo'] == 'https://www.javbus.com/pics/actress/ghi789_a.jpg'


def test_javbus_actor_manifest_declares_only_actor_capability(library):
    manager = Plugins(library)
    manifest = manager.install(Path(__file__).parents[1] / 'plugins' / 'javbus-actors')
    assert manifest['capabilities'] == ['actors']
    assert set(manifest['domains']) == {'www.javbus.com', 'javbus.com', 'r.jina.ai'}


def test_javbus_actor_is_an_allowed_builtin_actor_source(library):
    manager = Plugins(library)
    manager.update_builtin_actor_plugin('javbus-actors')
    item = manager.installed()[0]
    assert item['id'] == 'javbus-actors'
    assert not item['config']['enabled']


def test_javdb_actor_search_parses_aliases_and_placeholder(library, monkeypatch):
    manager = provider(library, 'javdb-actors')
    calls = []

    def fetch(plugin, url, image=False):
        calls.append(url)
        return JAVDB_SEARCH.encode('utf-8'), 'text/html; charset=utf-8'

    monkeypatch.setattr(manager, 'fetch', fetch)
    rows = manager.run('javdb-actors', 'actors', query='麻里梨夏')
    query = parse_qs(urlsplit(calls[0]).query)
    assert urlsplit(calls[0]).path == '/search' and query['f'] == ['actor'] and query['q'] == ['麻里梨夏']
    assert len(rows) == 2
    first = rows[0]
    assert first['id'] == 'javdb:G9P5'
    assert first['name'] == '麻里梨夏'
    assert first['gender'] == 'unknown'
    assert first['aliases'] == ['涼野しずく', '成海うるみ']
    assert first['url'] == 'https://javdb.com/actors/G9P5'
    assert first['photo'] == 'https://c0.jdbstatic.com/avatars/g9/G9P5.jpg'
    assert first['photo_page'] == first['url']
    assert 'title' not in first
    assert rows[1]['id'] == 'javdb:g0qVA' and not rows[1].get('photo')
    assert library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0] == 0


def test_javdb_actor_search_reports_cloudflare_challenge(library, monkeypatch):
    manager = provider(library, 'javdb-actors')
    page = '<html><head><title>Just a moment...</title></head><body>__cf_chl</body></html>'
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: (page.encode('utf-8'), 'text/html'))
    with pytest.raises(RuntimeError, match='Cloudflare'):
        manager.run('javdb-actors', 'actors', query='Sample')


def test_javdb_actor_search_returns_empty_without_actor_cards(library, monkeypatch):
    manager = provider(library, 'javdb-actors')
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: ('<div class="empty">no result</div>'.encode('utf-8'), 'text/html'))
    assert manager.run('javdb-actors', 'actors', query='Nobody') == []


def test_javdb_actor_manifest_and_builtin_allowlist(library):
    manager = Plugins(library)
    manifest = manager.install(Path(__file__).parents[1] / 'plugins' / 'javdb-actors')
    assert manifest['capabilities'] == ['actors']
    assert set(manifest['domains']) == {'javdb.com', 'c0.jdbstatic.com'}
    manager.update_builtin_actor_plugin('javdb-actors')
    item = manager.installed()[0]
    assert item['id'] == 'javdb-actors' and not item['config']['enabled']


JAVRATE_SEARCH = '''Title: 女優A片在綫免費播放 | Javrate
URL Source: https://www.javrate.com/actor/list/%E9%BA%BB%E9%87%8C%E6%A2%A8%E5%A4%8F

Markdown Content:
# 全部AV女優 名字包含 『麻里梨夏』的

共找到AV女優1人

[![Image 14: 麻里梨夏](https://picture.avking.xyz/compressed/20230522/fb513b24-1f08-4802-aa05-c7d5baa66304_s.webp) ### 麻里梨夏 7部AV 33 歲 148 cm 85-56-84 | D 罩杯 美人](https://www.javrate.com/actor/detail/3b580139-90be-4514-8cc9-24ecaaf6b356.html "麻里梨夏")

查找:

## 本月出道女優

[![Image 15: 喜多美愛梨 封面](https://picture.avking.xyz/compressed/20261022/cc9016a8-54b3-435d-9f4d-2d17428b4fe6_thumbnail.webp) ### 喜多美愛梨 43 歲](https://www.javrate.com/actor/detail/a1cad6bf-910c-4716-a9db-3b543fe3f406.html "喜多美愛梨")
'''


def test_javrate_actor_search_upgrades_portrait_and_ignores_sidebar(library, monkeypatch):
    manager = provider(library, 'javrate-actors')
    calls = []

    def fetch(plugin, url, image=False):
        calls.append(url)
        return JAVRATE_SEARCH.encode('utf-8'), 'text/plain; charset=utf-8'

    monkeypatch.setattr(manager, 'fetch', fetch)
    rows = manager.run('javrate-actors', 'actors', query='麻里梨夏')
    assert calls == ['https://r.jina.ai/https://www.javrate.com/actor/list/%E9%BA%BB%E9%87%8C%E6%A2%A8%E5%A4%8F']
    assert len(rows) == 1
    row = rows[0]
    assert row['id'] == 'javrate:3b580139-90be-4514-8cc9-24ecaaf6b356'
    assert row['name'] == '麻里梨夏'
    assert row['gender'] == 'female'
    assert row['aliases'] == []
    assert row['photo'] == 'https://picture.avking.xyz/compressed/20230522/fb513b24-1f08-4802-aa05-c7d5baa66304_l.webp'
    assert row['url'] == 'https://www.javrate.com/actor/detail/3b580139-90be-4514-8cc9-24ecaaf6b356.html'
    assert row['photo_page'] == row['url']
    assert library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0] == 0


def test_javrate_build_request_supports_direct_base(library):
    manager = provider(library, 'javrate-actors')
    request = manager.javascript('javrate-actors', 'buildRequest', {
        'operation': 'actors', 'config': {'base_url': 'https://www.javrate.com'}, 'query': 'Sample Name'})
    assert request['url'] == 'https://www.javrate.com/actor/list/sample%20name'


def test_javrate_actor_returns_empty_for_zero_results(library, monkeypatch):
    manager = provider(library, 'javrate-actors')
    page = '# 全部AV女優 名字包含 『Nobody』的\n共找到AV女優0人\n查找:\n'
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: (page.encode('utf-8'), 'text/plain'))
    assert manager.run('javrate-actors', 'actors', query='Nobody') == []


def test_javrate_reader_failure_is_reported(library, monkeypatch):
    manager = provider(library, 'javrate-actors')
    page = 'Title: Just a moment...\nMarkdown Content:\nCloudflare 403 Forbidden'
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: (page.encode('utf-8'), 'text/plain'))
    with pytest.raises(RuntimeError, match='JavRate'):
        manager.run('javrate-actors', 'actors', query='Sample')


def test_javrate_actor_manifest_and_builtin_allowlist(library):
    manager = Plugins(library)
    manifest = manager.install(Path(__file__).parents[1] / 'plugins' / 'javrate-actors')
    assert manifest['capabilities'] == ['actors']
    assert set(manifest['domains']) == {'r.jina.ai', 'www.javrate.com', 'picture.avking.xyz'}
    manager.update_builtin_actor_plugin('javrate-actors')
    item = manager.installed()[0]
    assert item['id'] == 'javrate-actors' and not item['config']['enabled']


def test_tvmaze_people_search_has_independent_schema(library, monkeypatch):
    manager = provider(library)
    response = [{'person': {'id': 9, 'name': 'Sample Actor', 'gender': 'Female', 'url': 'https://www.tvmaze.com/people/9/person',
                            'image': {'original': 'https://static.tvmaze.com/person.jpg'}, 'birthday': '1990-01-01'}},
                {'person': {'id': 10, 'name': 'No portrait', 'gender': 'Female', 'url': 'https://www.tvmaze.com/people/10/person', 'image': None}}]
    requests = []
    def fetch(plugin, url, image=False):
        requests.append(url); return json.dumps(response).encode(), 'application/json'
    monkeypatch.setattr(manager, 'fetch', fetch)
    rows = manager.run('tvmaze', 'actors', query='Sample Actor')
    assert len(rows) == 1 and rows[0]['name'] == 'Sample Actor' and 'title' not in rows[0]
    assert parse_qs(urlsplit(requests[0]).query)['q'] == ['Sample Actor']
    assert library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0] == 0
    assert library.db.execute('SELECT status FROM tasks ORDER BY updated DESC LIMIT 1').fetchone()[0] == 'done'


def test_wikimedia_follows_entity_and_commons_context(library, monkeypatch):
    manager = provider(library, 'wikimedia-actors')
    calls = []
    def claim(value): return [{'mainsnak': {'datavalue': {'value': value}}}]
    def fetch(plugin, url, image=False):
        calls.append(url); query = parse_qs(urlsplit(url).query)
        if query.get('action') == ['wbsearchentities']:
            value = {'search': [{'id': 'Q42'}]}
        elif query.get('action') == ['wbgetentities']:
            value = {'entities': {'Q42': {'labels': {'ja': {'value': 'Sample Actor'}, 'en': {'value': 'English name'}},
                'aliases': {'ja': [{'value': 'Alias'}]}, 'claims': {'P31': claim({'id': 'Q5'}),
                'P21': claim({'id': 'Q6581072'}), 'P18': claim('Public portrait.jpg')}}}}
        else:
            assert query['titles'] == ['File:Public portrait.jpg']
            value = {'query': {'pages': {'1': {'imageinfo': [{'url': 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Public_portrait.jpg',
                'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Public_portrait.jpg',
                'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'}, 'Artist': {'value': 'Photographer'}}}]}}}}
        return json.dumps(value).encode(), 'application/json'
    monkeypatch.setattr(manager, 'fetch', fetch)
    records = manager.run('wikimedia-actors', 'actors', query='Sample Actor')
    assert len(calls) == 3 and records[0]['id'] == 'wikidata:Q42'
    assert records[0]['aliases'] == ['English name', 'Alias']
    assert records[0]['photo_license'] == 'CC BY-SA 4.0'
    assert records[0]['photo'].startswith('https://upload.wikimedia.org/')


@pytest.mark.parametrize('record', [
    {'id': 'x', 'name': '', 'url': 'https://example.org'},
    {'id': 'x', 'name': 'Actor', 'url': 'file:///tmp/a'},
    {'id': 'x', 'name': 'Actor', 'url': 'https://example.org', 'photo': 'file:///tmp/a'},
    {'id': 'x', 'name': 'Actor', 'url': 'https://example.org', 'aliases': 'Alias'},
])
def test_actor_records_reject_invalid_schema(record):
    with pytest.raises(ValueError): validate_actor(record)


def test_portrait_updates_matching_credits_preserving_locks_and_existing(library, qapp, monkeypatch):
    manager = provider(library)
    old = library.directory / 'cache' / 'old.jpg'; old.write_bytes(portrait(qapp, 'red'))
    ids = [credit(library, 'Missing'), credit(library, 'Existing', photo=old),
           credit(library, 'Locked', locked=True), credit(library, 'Other', 'Other actor')]
    fetched = []
    def fetch(plugin, url, image=False):
        fetched.append((url, image)); return portrait(qapp), 'image/png'
    monkeypatch.setattr(manager, 'fetch', fetch)
    record = {**candidate(), 'photo_page': 'https://example.org/license',
              'photo_license': 'CC BY 4.0', 'photo_attribution': '<b>Artist</b>'}
    result = manager.merge_actor('tvmaze', record, 'Local alias')
    assert result == {'updated': 1, 'skipped': 2, 'name': 'Local alias'}
    actor = library.work(ids[0])['metadata']['actors'][0]
    assert actor['name'] == 'Local actor' and actor['aliases'] == ['Local alias']
    assert Path(actor['photo_cache']).is_file() and actor['photo_attribution'] == 'Artist'
    assert library.work(ids[1])['metadata']['actors'][0]['photo_cache'] == str(old)
    assert 'photo_cache' not in library.work(ids[2])['metadata']['actors'][0]
    assert 'photo_cache' not in library.work(ids[3])['metadata']['actors'][0]
    result = manager.merge_actor('tvmaze', record, 'Local actor', replace=True)
    assert result['updated'] == 2 and len(fetched) == 2
    assert library.work(ids[0])['metadata']['overview'] == 'Keep this'


def test_network_request_does_not_hold_write_transaction_or_erase_new_edits(library, qapp, monkeypatch):
    manager = provider(library); work_id = credit(library, 'Concurrent edits')
    def fetch(plugin, url, image=False):
        assert not library.db.in_transaction
        library.edit_metadata(work_id, {'overview': 'Edited while downloading'}, [])
        return portrait(qapp), 'image/png'
    monkeypatch.setattr(manager, 'fetch', fetch)
    assert manager.merge_actor('tvmaze', candidate(), 'Local actor')['updated'] == 1
    assert library.work(work_id)['metadata']['overview'] == 'Edited while downloading'


def test_failed_image_does_not_change_cast(library, qapp, monkeypatch):
    manager = provider(library); work_id = credit(library, 'Corrupt portrait')
    original = library.work(work_id)['metadata']
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: (b'not an image', 'image/jpeg'))
    with pytest.raises(ValueError, match='尺寸'): manager.merge_actor('tvmaze', candidate(), 'Local actor')
    assert library.work(work_id)['metadata'] == original


def test_builtin_update_preserves_user_configuration_without_enabling(library):
    manager = Plugins(library)
    manager.update_builtin_actor_plugin('tvmaze')
    assert not manager.installed()[0]['config']['enabled']
    manager.configure('tvmaze', {'enabled': True, 'proxy': 'http://127.0.0.1:8899', 'priority': 17})
    manifest_path = manager.root / 'tvmaze' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')); manifest['capabilities'].remove('actors')
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    manager.update_builtin_actor_plugin('tvmaze')
    current = manager.installed()[0]
    assert 'actors' in current['capabilities'] and current['config']['enabled']
    assert current['config']['proxy'] == 'http://127.0.0.1:8899' and current['config']['priority'] == 17
    with pytest.raises(ValueError): manager.update_builtin_actor_plugin('other-plugin')


def test_lan_cached_portrait_authentication_and_path_boundary(lan, library, qapp):
    client, server, _, _ = lan
    work_id = library.query()[0]['id']; path = library.directory / 'cache' / 'actor.jpg'
    data = portrait(qapp); path.write_bytes(data)
    library.edit_metadata(work_id, {'actors': [{'name': 'Actor', 'gender': 'female', 'photo_cache': str(path),
                                              'photo_license': 'CC BY 4.0'}]}, [])
    actor = client.get(f'/api/works/{work_id}').json()['actors'][0]
    assert actor['photo_license'] == 'CC BY 4.0' and 'photo_cache' not in actor
    assert client.get(actor['photo']).content == data
    assert client.get(actor['photo'], headers={'Authorization': ''}).status_code == 401
    assert client.get(f'/api/works/{work_id}/actors/99/photo').status_code == 404
    library.edit_metadata(work_id, {'actors': [{'name': 'Actor', 'photo_cache': str(path.parent.parent / 'library.db')}]}, [])
    assert client.get(actor['photo']).status_code == 403


def test_changed_portrait_at_same_source_url_gets_new_android_cache_key(lan, library, qapp, monkeypatch):
    """The client caches by URL; updated bytes therefore need a revised URL."""
    import hashlib
    client, _, _, _ = lan
    work_id = library.query()[0]['id']
    library.edit_metadata(work_id, {'actors': [{'name': 'Local actor', 'gender': 'female'}]}, [])
    manager = provider(library)
    content = [portrait(qapp, 'red')]
    monkeypatch.setattr(manager, 'fetch', lambda *args, **kwargs: (content[0], 'image/png'))
    manager.merge_actor('tvmaze', candidate(), 'Local actor')
    first_actor = library.work(work_id)['metadata']['actors'][0]
    old_image_path = Path(first_actor['photo_cache'])
    first_url = client.get(f'/api/works/{work_id}').json()['actors'][0]['photo']
    assert parse_qs(urlsplit(first_url).query)['v'] == [hashlib.sha256(content[0]).hexdigest()]
    first_image = client.get(first_url).content
    assert first_image.startswith(b'\xff\xd8')
    android_cache = {first_url: first_image}
    content[0] = portrait(qapp, 'blue')
    manager.merge_actor('tvmaze', candidate(), 'Local actor', replace=True)
    second_actor = library.work(work_id)['metadata']['actors'][0]
    second_url = client.get(f'/api/works/{work_id}').json()['actors'][0]['photo']
    assert second_url != first_url and second_url not in android_cache
    assert first_actor['photo'] == second_actor['photo']
    assert old_image_path != Path(second_actor['photo_cache']) and old_image_path.read_bytes() == first_image
    second_response = client.get(second_url)
    assert second_response.status_code == 200 and second_response.content != first_image
    assert second_actor['photo_revision'] == hashlib.sha256(content[0]).hexdigest()
