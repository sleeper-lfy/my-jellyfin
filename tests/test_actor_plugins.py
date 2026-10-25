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
