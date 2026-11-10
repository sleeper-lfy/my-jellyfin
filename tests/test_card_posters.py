"""Portrait movie/VR cards share the LAN poster role without changing thumbnail mode."""
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage, QColor

from lumen.artwork_ui import save_artwork
from lumen.ui import MainWindow
from test_core import add_work


def picture(path, width, height, color):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path))
    return str(path)


def fixture_work(library, kind):
    identifier = add_work(library, 'Coast Journal ' + kind, kind=kind)
    digest = ('a' if kind == 'movie' else 'b') * 64
    frame = library.directory / 'cache' / (digest + '.jpg')
    picture(frame, 480, 270, 'steelblue')
    with library.db:
        library.db.execute('UPDATE files SET digest=? WHERE work_id=?', (digest, identifier))
        library.db.execute('UPDATE works SET thumbnail=? WHERE id=?', (str(frame), identifier))
    return identifier, frame


def view(library, mode='poster'):
    return SimpleNamespace(library=library, view_mode=SimpleNamespace(currentData=lambda: mode))


@pytest.mark.parametrize('kind', ['movie', 'vr'])
def test_portrait_cards_choose_saved_poster_and_keep_the_file_frame_for_thumbnail_mode(library, qapp, tmp_path, kind):
    identifier, frame = fixture_work(library, kind)
    source = tmp_path / 'coast-poster.png'
    picture(source, 240, 360, 'seagreen')
    save_artwork(library, identifier, source, 'poster', 'center')
    selected = library.setting(f'artwork_{identifier}')['poster']
    work = library.work(identifier)
    portrait = MainWindow.card_data(view(library), work)
    assert portrait['_landscape'] is False
    assert portrait['_cover'] == portrait['thumbnail'] == selected
    landscape = MainWindow.card_data(view(library), work, True)
    assert landscape['_landscape'] is True and landscape['_cover'] == str(frame)
    assert library.work(identifier)['thumbnail'] == str(frame)


@pytest.mark.parametrize('kind', ['movie', 'vr'])
def test_frame_only_portrait_card_cannot_fall_back_to_the_legacy_thumbnail(library, qapp, kind):
    identifier, frame = fixture_work(library, kind)
    card = MainWindow.card_data(view(library), library.work(identifier))
    assert card['_cover'] is None and card['thumbnail'] is None
    assert not (card.get('_cover') or card.get('thumbnail') or card.get('photo_cache'))
    assert library.work(identifier)['thumbnail'] == str(frame)


@pytest.mark.parametrize('kind', ['movie', 'vr'])
def test_explicit_global_thumbnail_mode_remains_a_thumbnail_view(library, qapp, kind):
    identifier, frame = fixture_work(library, kind)
    card = MainWindow.card_data(view(library, 'thumbnail'), library.work(identifier))
    assert card['_landscape'] is True
    assert card['_cover'] == str(frame)
