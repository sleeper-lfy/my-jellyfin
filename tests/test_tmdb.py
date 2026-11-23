import json
from urllib.parse import parse_qs, urlsplit

import pytest

from lumen import tmdb
from lumen.numbered_sources import SourceLookupError, resolve
from lumen.plugin_access import PluginHttpError, check_response
from lumen.plugins import Plugins


TOKEN = 'mockHeader.mockPayload.mockSignature'


@pytest.fixture
def provider(library, monkeypatch):
    tmdb.save_settings(library, TOKEN, True)
    show = {
        'id': 123, 'name': '星海旅人', 'original_name': '星の旅人', 'first_air_date': '2024-10-03',
        'poster_path': '/poster.jpg', 'backdrop_path': '/backdrop.jpg', 'overview': '从地球启程。',
        'vote_average': 8.2, 'vote_count': 29, 'genres': [{'id': 16, 'name': '动画'}],
        'external_ids': {'imdb_id': 'tt1234567', 'tvdb_id': 45},
        'credits': {'cast': [{'id': 1, 'name': '声优甲', 'gender': 1, 'profile_path': '/portrait.jpg'}]},
    }
    movie = {'id': 123, 'title': '飞船 13', 'original_title': 'Spaceship 13', 'release_date': '2024-05-01'}
    requests = []

    def fetch(manager, plugin, url, image=False):
        manager._approved_url(plugin, url)
        assert manager._request_headers(plugin, url)['Authorization'] == 'Bearer ' + TOKEN
        parsed = urlsplit(url)
        assert TOKEN not in url and 'token' not in plugin['config']
        parameters = parse_qs(parsed.query)
        assert parameters['language'] == ['zh-CN']
        requests.append((parsed.path, parameters))
        if parsed.path == '/3/search/multi':
            result = {'results': [dict(movie, media_type='movie'), dict(show, media_type='tv'),
                                  {'id': 3, 'media_type': 'person', 'name': 'Person'}]}
        elif parsed.path == '/3/search/movie':
            result = {'results': [movie]}
        elif parsed.path == '/3/search/tv':
            result = {'results': [show]}
        else:
            result = {'/3/movie/123': movie, '/3/tv/123': show}[parsed.path]
        return json.dumps(result).encode(), 'application/json'

    monkeypatch.setattr(Plugins, 'fetch', fetch)
    return Plugins(library), requests


def test_bundled_tmdb_search_details_and_canonical_media_ids(provider):
    manager, requests = provider
    records = manager.run(tmdb.ID, 'search', query='同名电影与剧集')
    assert [(item['id'], item['kind']) for item in records] == [('movie:123', 'movie'), ('tv:123', 'series')]
    show, = manager.run(tmdb.ID, 'detail', url='https://www.themoviedb.org/tv/123-star-voyager?language=ja')
    assert (show['title'], show['year'], show['tags'], show['aliases']) == ('星海旅人', 2024, ['动画'], ['星の旅人'])
    assert show['external_ids'] == {'tmdb': '123', 'imdb': 'tt1234567', 'tvdb': '45'}
    assert show['poster'] == 'https://image.tmdb.org/t/p/w500/poster.jpg'
    assert show['cover'] == 'https://image.tmdb.org/t/p/w1280/backdrop.jpg'
    assert show['actors'][0]['photo'] == 'https://image.tmdb.org/t/p/w185/portrait.jpg'
    assert show['rating'] == 8.2
    assert requests[-1][1]['append_to_response'] == ['credits,external_ids,alternative_titles']
    with pytest.raises(RuntimeError, match='类型不匹配'):
        manager.run(tmdb.ID, 'detail', url=show['url'], kind='movie')
    with pytest.raises(RuntimeError, match='详情页链接'):
        manager.run(tmdb.ID, 'detail', url='https://unlisted.example.org/tv/123')
    assert len(requests) == 2


def test_automatic_matching_uses_scoped_title_and_original_names(library, provider):
    _, requests = provider
    movie = {'title': 'Spaceship 13', 'year': 2024, 'kind': 'movie', 'files': [{'path': '/media/Spaceship 13.mkv'}]}
    assert resolve(library, movie, 'tmdb')['candidate']['title'] == '飞船 13'
    assert requests[0][0] == '/3/search/movie' and requests[0][1]['query'] == ['Spaceship 13']
    show = {'title': '星の旅人（2024）', 'year': 2024, 'kind': 'series', 'files': []}
    assert resolve(library, show, 'tmdb')['candidate']['id'] == 'tv:123'
    assert requests[-2][0] == '/3/search/tv'
    assert requests[-2][1]['query'] == ['星の旅人']
    with pytest.raises(SourceLookupError) as mismatch:
        resolve(library, dict(movie, year=2014), 'tmdb')
    assert mismatch.value.candidates[0]['id'] == 'movie:123'
    assert not mismatch.value.retryable
    assert requests[-1][0] == '/3/search/movie'


def test_tmdb_can_refresh_local_movie_metadata_without_changing_personal_state(library, provider):
    from lumen.metadata_health import repair_many
    from test_core import add_work

    work_id = add_work(library, 'Spaceship 13', metadata={'overview': 'Old summary'})
    with library.db:
        library.db.execute('UPDATE works SET rating=9, favorite=1, watchlist=1 WHERE id=?', (work_id,))
    result = repair_many(library, [work_id], force=True, plugin_ids=[tmdb.ID])
    assert result['updated'] == 1 and result['failed'] == 0
    work = library.work(work_id)
    assert work['title'] == '飞船 13'
    assert work['metadata']['external_ids']['tmdb'] == '123'
    assert (work['rating'], work['favorite'], work['watchlist']) == (9, 1, 1)
    assert work['sources'][0]['source_id'] == 'movie:123'


def test_credentials_stay_out_of_plugin_config_and_are_origin_scoped(library):
    manager = Plugins(library)
    assert manager.installed() == []
    with pytest.raises(ValueError, match='读取访问令牌'):
        tmdb.save_settings(library, '0' * 32, True)
    tmdb.save_settings(library, TOKEN, True)
    manifest, = manager.installed()
    assert 'token' not in manifest['config']
    assert manager._request_headers(manifest, 'https://api.themoviedb.org/3/search/movie')['Authorization'] == 'Bearer ' + TOKEN
    for url in ('https://image.tmdb.org/t/p/w500/poster.jpg', 'http://api.themoviedb.org/3/movie/123',
                'https://api.themoviedb.org:8080/3/movie/123', 'https://api.themoviedb.org.evil.test/3/movie/123'):
        assert 'Authorization' not in manager._request_headers(manifest, url)
    with pytest.raises(ValueError, match='官方 HTTPS'):
        manager._approved_url(manifest, 'http://api.themoviedb.org/3/movie/123')
    with pytest.raises(PluginHttpError, match='影视刮削'):
        check_response(401, {}, b'{}', manifest['base_url'])
    tmdb.save_settings(library, TOKEN, False)
    with pytest.raises(ValueError, match='未启用'):
        manager.run(tmdb.ID, 'search', query='动画')


def test_desktop_settings_expose_tmdb_in_supported_library_source_lists(qapp, library):
    from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton
    from lumen.media_management_ui import add_provider_items
    from lumen.tmdb_ui import TmdbSettings

    panel = TmdbSettings(library)
    assert panel.token.echoMode() == QLineEdit.EchoMode.Password
    logo = next(label for label in panel.findChildren(QLabel) if label.accessibleName() == 'The Movie Database')
    assert not logo.pixmap().isNull()
    panel.token.setText(TOKEN)
    panel.enabled.setChecked(True)
    panel.findChild(QPushButton, 'saveTmdbSettings').click()
    for kind in ('movie', 'series', 'vr', 'other'):
        combo = QComboBox()
        add_provider_items(combo, library, '', kind=kind)
        assert (combo.findData(tmdb.ID) >= 0) == (kind in {'movie', 'series'})
