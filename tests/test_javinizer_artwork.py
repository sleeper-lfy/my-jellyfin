import hashlib
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from lumen import javinizer as engine
from lumen.artwork import scraped_image_path, thumbnail_path
from lumen.artwork_ui import artwork_paths
from lumen.core import ImportCancelled, Library
from lumen.plugins import Plugins
from test_core import add_work
from test_javinizer import raw


POSTER = 'https://pics.dmm.co.jp/poster.jpg'
COVER = 'https://pics.dmm.co.jp/cover.jpg'
STILL = 'https://pics.dmm.co.jp/still.jpg'


def image_bytes(tmp_path, name, size, color):
    image = QImage(*size, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    path = tmp_path / (name + '.png')
    assert image.save(str(path))
    return path.read_bytes()


def setup_images(library, monkeypatch, images):
    engine.save_settings(library, {'enabled': True})
    requests = []

    def fetch(self, plugin, url, image=False):
        assert not self.library.db.in_transaction
        requests.append(url)
        data = images[url]
        if isinstance(data, Exception):
            raise data
        return data, 'image/png'

    monkeypatch.setattr(Plugins, 'fetch', fetch)
    return Plugins(library), requests


def record(poster=POSTER, cover=COVER, stills=None):
    return engine.metadata(raw(poster_url=poster, cover_url=cover,
                               screenshot_urls=stills or [], actresses=[]), 'r18dev', 'IPX-535')


def test_mapping_keeps_cover_and_rejects_untrusted_urls():
    mapped = record()
    assert mapped['poster'] == POSTER and mapped['cover'] == COVER
    assert not record(cover='file:///secret')['cover']
    assert not record(cover='https://unknown.test/cover')['cover']
    assert not record(poster='', cover='https://user:password@pics.dmm.co.jp/cover')['poster']


@pytest.mark.parametrize('poster_size,has_cover,has_still', [
    ((200, 300), True, False),  # Preserve distinct portrait and landscape images.
    (None, True, False),        # Only a cover: crop a poster, retain the original.
    ((200, 300), False, False), # Only a poster: both views remain usable.
    ((640, 360), False, False), # A wide image in poster_url must also be normalized.
    (None, False, True),        # Only screenshots: use the existing still fallback.
])
def test_partial_artwork_has_valid_poster_and_thumbnail_after_reopen(
        library, qapp, tmp_path, monkeypatch, poster_size, has_cover, has_still):
    images = {}
    if poster_size:
        images[POSTER] = image_bytes(tmp_path, 'poster', poster_size, 'blue')
    if has_cover:
        images[COVER] = image_bytes(tmp_path, 'cover', (640, 360), 'red')
    if has_still:
        images[STILL] = image_bytes(tmp_path, 'still', (640, 360), 'green')
    manager, requests = setup_images(library, monkeypatch, images)
    mapped = record(POSTER if poster_size else '', COVER if has_cover else '', [STILL] if has_still else [])
    identifier = manager.merge(engine.ENGINE_ID, mapped)
    work = library.work(identifier)
    poster = QImage(work['thumbnail'])
    assert not poster.isNull() and poster.width() / poster.height() == pytest.approx(2 / 3, abs=.01)
    thumbnail = thumbnail_path(library, work)
    assert not QImage(thumbnail).isNull()
    if has_cover:
        assert thumbnail == scraped_image_path(work, 'cover')
        assert QImage(thumbnail).pixelColor(20, 20).red() > 240
    if has_cover or has_still or poster_size == (640, 360):
        assert QImage(thumbnail).width() == 640
        assert thumbnail != work['thumbnail']
    assert thumbnail in artwork_paths(library, work)
    assert len(requests) == len(images)  # A shared poster/cover URL downloads once.
    before = Path(thumbnail).read_bytes()
    manager.merge(engine.ENGINE_ID, mapped, identifier)
    assert len(requests) == len(images) and Path(thumbnail).read_bytes() == before
    reopened = Library(library.directory)
    try:
        assert reopened.work(identifier)['thumbnail'] == work['thumbnail']
        assert thumbnail_path(reopened, reopened.work(identifier)) == thumbnail
    finally:
        reopened.close()


@pytest.mark.parametrize('failed', [POSTER, COVER])
def test_one_download_failure_uses_the_other_image(library, qapp, tmp_path, monkeypatch, failed):
    images = {POSTER: image_bytes(tmp_path, 'poster', (200, 300), 'blue'),
              COVER: image_bytes(tmp_path, 'cover', (640, 360), 'red')}
    images[failed] = ValueError('HTTP 403')
    manager, _ = setup_images(library, monkeypatch, images)
    identifier = manager.merge(engine.ENGINE_ID, record())
    work = library.work(identifier)
    assert not QImage(work['thumbnail']).isNull()
    assert not QImage(thumbnail_path(library, work)).isNull()
    assert QImage(work['thumbnail']).width() / QImage(work['thumbnail']).height() == pytest.approx(2 / 3, abs=.01)
    assert library.db.execute("SELECT count(*) FROM tasks WHERE kind='image' AND status='failed'").fetchone()[0] == 1
    images[failed] = image_bytes(tmp_path, 'retry', (200, 300) if failed == POSTER else (640, 360), 'green')
    manager.merge(engine.ENGINE_ID, record(), identifier)
    assert scraped_image_path(library.work(identifier), 'poster')
    assert scraped_image_path(library.work(identifier), 'cover')


@pytest.mark.parametrize('protection', ['manual', 'locked', 'nfo'])
def test_fallback_preserves_protected_artwork(library, qapp, tmp_path, monkeypatch, protection):
    identifier = add_work(library, 'Protected')
    saved = tmp_path / 'protected.png'
    saved.write_bytes(image_bytes(tmp_path, 'source', (300, 200), 'green'))
    library.edit_metadata(identifier, {'nfo_poster': True} if protection == 'nfo' else {},
                          ['poster'] if protection == 'locked' else [])
    with library.db:
        library.db.execute('UPDATE works SET thumbnail=? WHERE id=?', (str(saved), identifier))
    if protection == 'manual':
        library.set_setting(f'artwork_{identifier}', {'poster': str(saved), 'thumbnail': str(saved)})
    manager, _ = setup_images(library, monkeypatch, {COVER: image_bytes(tmp_path, 'cover', (640, 360), 'red')})
    manager.merge(engine.ENGINE_ID, record(poster=''), identifier)
    work = library.work(identifier)
    assert work['thumbnail'] == str(saved)
    if protection == 'manual':
        assert thumbnail_path(library, work) == str(saved)


def test_corrupt_cached_image_is_retried(library, qapp, tmp_path, monkeypatch):
    manager, requests = setup_images(library, monkeypatch,
                                    {COVER: image_bytes(tmp_path, 'cover', (640, 360), 'red')})
    cached = library.directory / 'cache' / ('javinizer-' + hashlib.sha256(COVER.encode()).hexdigest() + '.jpg')
    cached.write_bytes(b'broken image')
    identifier = manager.merge(engine.ENGINE_ID, record(poster=''))
    assert requests == [COVER] and not QImage(library.work(identifier)['thumbnail']).isNull()


def test_poster_fallback_rechecks_concurrent_manual_edit(library, qapp, tmp_path, monkeypatch):
    from lumen import artwork
    manager, _ = setup_images(library, monkeypatch,
                             {COVER: image_bytes(tmp_path, 'cover', (640, 360), 'red')})
    identifier = add_work(library, 'Concurrent')
    original = artwork.scraped_poster_path
    saved = tmp_path / 'manual.png'
    saved.write_bytes(image_bytes(tmp_path, 'manual', (200, 300), 'green'))

    def select(*args, **kwargs):
        assert not library.db.in_transaction
        result = original(*args, **kwargs)
        other = Library(library.directory)
        try:
            other.edit_metadata(identifier, {'overview': 'Saved during fallback'}, ['poster'])
            with other.db:
                other.db.execute('UPDATE works SET thumbnail=? WHERE id=?', (str(saved), identifier))
        finally:
            other.close()
        return result

    monkeypatch.setattr(artwork, 'scraped_poster_path', select)
    manager.merge(engine.ENGINE_ID, record(poster=''), identifier)
    work = library.work(identifier)
    assert work['thumbnail'] == str(saved) and work['metadata']['overview'] == 'Saved during fallback'


def test_cancelled_image_task_does_not_apply_fallback(library, qapp, tmp_path, monkeypatch):
    manager, _ = setup_images(library, monkeypatch, {})
    identifier = add_work(library, 'Cancelled')
    with pytest.raises(ImportCancelled):
        engine.cache_images(library, record(poster='', cover=''), identifier, cancelled=lambda: True)
    assert library.work(identifier)['thumbnail'] is None


def test_plugin_cannot_inject_artwork_cache_paths(library, monkeypatch):
    manager, _ = setup_images(library, monkeypatch, {})
    identifier = manager.merge(engine.ENGINE_ID, {**record(poster='', cover=''),
        'poster_cache': {'url': None, 'path': '/secret'}, 'cover_cache': {'url': None, 'path': '/secret'}})
    assert 'poster_cache' not in library.work(identifier)['metadata']
    assert 'cover_cache' not in library.work(identifier)['metadata']
