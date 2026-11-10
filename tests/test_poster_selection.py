"""Poster-mode LAN cards use the same role as desktop, never a video-frame fallback."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from PySide6.QtGui import QImage, QColor

from lumen.artwork import poster_path
from lumen.artwork_ui import save_artwork
from lumen.server import LanServer
from test_core import add_work
from test_discovery_search import site


def picture(path, color, width=200, height=300):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path))
    return path.read_bytes()


@pytest.fixture
def poster_lan(library, video_factory, request):
    source = video_factory('Poster role.2024.mp4')
    library.import_folder(source.parent, 'movie', fast=True)
    work = library.query()[0]
    file = work['files'][0]
    frame = library.directory/'cache'/(file['digest']+'.jpg')
    picture(frame, 'blue', 480, 270)
    with library.db:
        library.db.execute('UPDATE works SET kind=?,thumbnail=? WHERE id=?',
            (getattr(request, 'param', 'movie'), str(frame), work['id']))
        library.db.execute('UPDATE files SET position=1,duration=4 WHERE id=?', (file['id'],))
    server = LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=None)
    server.start()
    with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
        yield client, server, work['id'], file, frame
    server.stop()


def update(library, identifier, metadata):
    with library.db:
        library.db.execute('UPDATE works SET metadata=? WHERE id=?', (json.dumps(metadata), identifier))


@pytest.mark.parametrize('poster_lan', ['movie','vr'], indirect=True)
def test_manual_poster_and_same_work_thumbnail_are_different_roles(library, poster_lan):
    client, _, identifier, file, frame = poster_lan
    manual = library.directory/'cache'/'manual-poster.jpg'
    picture(manual, 'red')
    save_artwork(library, identifier, manual, 'poster', 'center')
    selected = poster_path(library, library.work(identifier))
    result = client.get('/api/works').json()['items'][0]
    assert result['cover'] == f'/api/works/{identifier}/cover'
    assert client.get(result['cover']).content == Path(selected).read_bytes()
    resume = client.get('/api/continue').json()['items'][0]['resume']
    assert resume['file_id'] == file['id']
    assert client.get(resume['thumbnail']).content == frame.read_bytes()
    assert client.get(result['cover'],headers={'Authorization':''}).status_code == 401


@pytest.mark.parametrize('poster_lan', ['movie','vr'], indirect=True)
def test_manual_only_gets_a_cover_url_without_listing_probes(library, poster_lan, monkeypatch):
    client, _, identifier, _, _ = poster_lan
    manual = library.directory/'cache'/'only-manual.jpg'
    expected = picture(manual, 'red')
    library.set_setting(f'artwork_{identifier}', {'poster':str(manual), 'thumbnail':str(manual)})
    with library.db:library.db.execute('UPDATE works SET thumbnail=NULL WHERE id=?', (identifier,))
    with monkeypatch.context() as listing:
        listing.setattr('lumen.artwork._poster_dimensions', lambda *args:pytest.fail('Listing must not probe/decode image headers'))
        result = client.get('/api/works').json()['items'][0]
    assert result['cover'] is not None
    assert client.get(result['cover']).content == expected


@pytest.mark.parametrize('poster_lan', ['movie','vr'], indirect=True)
def test_source_poster_cache_has_priority_over_a_legacy_frame(library, poster_lan):
    client, _, identifier, _, frame = poster_lan
    cached = library.directory/'cache'/'source-poster.jpg'
    expected = picture(cached, 'red')
    url = 'https://example.test/real-poster.jpg'
    update(library, identifier, {'poster':url,'poster_cache':{'url':url,'path':str(cached)}})
    assert client.get(f'/api/works/{identifier}/cover').content == expected
    assert library.work(identifier)['thumbnail'] == str(frame)


@pytest.mark.parametrize('poster_lan', ['movie','vr'], indirect=True)
def test_frame_only_cards_advertise_no_poster_and_the_cover_is_404(library, poster_lan):
    client, _, identifier, _, frame = poster_lan
    assert client.get('/api/works').json()['items'][0]['cover'] is None
    response = client.get(f'/api/works/{identifier}/cover')
    assert response.status_code == 404 and response.content != frame.read_bytes()


def test_explicit_nfo_poster_wins_even_when_the_same_image_is_also_a_thumb(library, poster_lan):
    client, _, identifier, file, _ = poster_lan
    cached = library.directory/'cache'/'nfo-poster.jpg'
    expected = picture(cached, 'red')
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(cached),identifier))
    update(library, identifier, {'nfo_poster':True,'nfo_thumbnails':{str(file['id']):str(cached)}})
    assert client.get(f'/api/works/{identifier}/cover').content == expected


@pytest.mark.parametrize('naming', ['plugin','preview'])
def test_old_current_url_poster_cache_is_reused_without_fetch(library, poster_lan, monkeypatch, naming):
    client, _, identifier, _, _ = poster_lan
    url = 'https://example.test/old-plugin-poster.jpg'
    update(library, identifier, {'poster':url})
    with library.db:
        library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',(identifier,'sample','Sample','id','https://example.test/item','now',None,None))
    name = hashlib.sha256(url.encode()).hexdigest() if naming == 'plugin' else 'match-'+hashlib.sha256(('sample'+url).encode()).hexdigest()
    expected = picture(library.directory/'cache'/(name+'.jpg'), 'red')
    monkeypatch.setattr('lumen.matching.preview_cover',lambda *a:pytest.fail('Cached current URL must not fetch again'))
    assert client.get(f'/api/works/{identifier}/cover').content == expected


def test_locked_real_legacy_poster_is_kept_but_locked_frames_are_rejected(library, poster_lan):
    client, _, identifier, _, frame = poster_lan
    legacy = library.directory/'cache'/'old-poster.jpg'
    expected = picture(legacy, 'green')
    replacement = library.directory/'cache'/'new-poster.jpg'
    picture(replacement, 'red')
    url = 'https://example.test/new.jpg'
    update(library, identifier, {'poster':url,'poster_cache':{'url':url,'path':str(replacement)}})
    with library.db:
        library.db.execute('UPDATE works SET thumbnail=?,locked=? WHERE id=?',(str(legacy),'["poster"]',identifier))
    assert client.get(f'/api/works/{identifier}/cover').content == expected
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(frame),identifier))
    assert client.get(f'/api/works/{identifier}/cover').status_code == 404


def test_unknown_legacy_image_must_actually_have_portrait_dimensions(library, poster_lan):
    client, _, identifier, _, _ = poster_lan
    legacy = library.directory/'cache'/'untyped.jpg'
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(legacy),identifier))
    picture(legacy, 'blue', 480,270)
    assert client.get(f'/api/works/{identifier}/cover').status_code == 404
    expected = picture(legacy, 'red')
    assert client.get(f'/api/works/{identifier}/cover').content == expected


def test_manual_poster_cache_boundary_and_symlinks_are_not_followed(library, poster_lan, tmp_path, monkeypatch):
    client, _, identifier, _, _ = poster_lan
    outside = tmp_path/'private-poster.jpg'
    picture(outside, 'red')
    library.set_setting(f'artwork_{identifier}', {'poster':str(outside)})
    response = client.get(f'/api/works/{identifier}/cover')
    assert response.status_code == 403 and str(outside) not in response.text
    inside = library.directory/'cache'/'symlink-poster.jpg'
    picture(inside, 'red')
    library.set_setting(f'artwork_{identifier}', {'poster':str(inside)})
    original = Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda path: path == inside or original(path))
    assert client.get(f'/api/works/{identifier}/cover').status_code == 403


def source_record(library, identifier, site):
    update(library, identifier, {'poster':site['base']+'/poster.png'})
    with library.db:
        library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',(identifier,'search-site','Site','poster-id',site['base']+'/details/poster','now',None,None))


def test_imported_frame_does_not_short_circuit_lazy_source_poster(library, poster_lan, site):
    client, _, identifier, _, frame = poster_lan
    source_record(library,identifier,site)
    url = client.get('/api/works').json()['items'][0]['cover']
    assert site['requests'] == []
    response = client.get(url)
    assert response.status_code == 200 and response.content != frame.read_bytes()
    assert site['requests'] == ['/poster.png']
    assert client.get(url).content == response.content and len(site['requests']) == 1
    current = library.work(identifier)
    assert current['thumbnail'] == str(frame)
    assert current['metadata']['poster_cache']['url'] == site['base']+'/poster.png'


@pytest.mark.parametrize('change', ['manual','locked','url','source','source_id','import'])
def test_lazy_poster_respects_changes_during_fetch(library, poster_lan, site, monkeypatch, change):
    client, _, _, _, _ = poster_lan
    identifier = add_work(library,'Metadata-only poster',local=False)
    source_record(library,identifier,site)
    url = site['base']+'/poster.png'
    fetched = library.directory/'cache'/('match-'+hashlib.sha256(('search-site'+url).encode()).hexdigest()+'.jpg')
    manual = library.directory/'cache'/'changed-manual.jpg'
    picture(manual,'green')
    def fetch(live, plugin, record):
        picture(fetched, 'red')
        with live.db:
            if change == 'manual':live.set_setting(f'artwork_{identifier}', {'poster':str(manual)})
            elif change == 'locked':live.db.execute('UPDATE works SET locked=? WHERE id=?',('["poster"]',identifier))
            elif change == 'url':live.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps({'poster':site['base']+'/changed.png'}),identifier))
            elif change == 'source':live.db.execute('DELETE FROM sources WHERE work_id=?',(identifier,))
            elif change == 'source_id':live.db.execute('UPDATE sources SET source_id=? WHERE work_id=?',('changed-source',identifier))
            else:live.db.execute('INSERT INTO files(work_id,path,digest,root,duration) VALUES (?,?,?,?,?)',(identifier,'/media/now-imported.mp4','new-file','/media',4))
        return str(fetched)
    monkeypatch.setattr('lumen.matching.preview_cover',fetch)
    response = client.get(f'/api/works/{identifier}/cover')
    assert response.status_code == (200 if change == 'manual' else 404)
    if change == 'manual':assert response.content == manual.read_bytes()
    assert 'poster_cache' not in library.work(identifier)['metadata']


def test_non_movie_lazy_errors_keep_the_existing_404_contract(library, poster_lan, monkeypatch):
    client, _, identifier, _, _ = poster_lan
    with library.db:library.db.execute('UPDATE works SET kind=?,thumbnail=NULL WHERE id=?',('series',identifier))
    monkeypatch.setattr('lumen.discovery_search.cache_discovery_cover', lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('unavailable')))
    assert client.get(f'/api/works/{identifier}/cover').status_code == 404
