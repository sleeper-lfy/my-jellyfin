"""Continue-watching previews are frames for the selected file, never posters."""
import json
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from PySide6.QtGui import QImage, QColor

from lumen.server import LanServer


def picture(path, color, width=160, height=90):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path))
    return path.read_bytes()


@pytest.fixture
def preview(library, video_factory):
    source = video_factory('Continue preview.2024.mp4')
    library.import_folder(source.parent, 'movie', fast=True)
    work = library.query()[0]
    file = work['files'][0]
    with library.db:
        library.db.execute('UPDATE files SET position=1,duration=4 WHERE id=?', (file['id'],))
    clock = [100.0]
    server = LanServer(library.directory, host='127.0.0.1', port=0,
                       discovery_port=None, clock=lambda: clock[0])
    server.start()
    with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',
                      headers={'Authorization': 'Bearer ' + server.token}, trust_env=False) as client:
        yield client, server, source, work, file, clock
    server.stop()


def set_artwork(library, work_id, poster, thumbnails):
    with library.db:
        library.db.execute('UPDATE works SET thumbnail=?,metadata=? WHERE id=?',
                           (str(poster), json.dumps({'nfo_thumbnails': thumbnails}), work_id))


def test_continue_lists_exact_file_thumbnail_and_does_not_decode(library, preview, monkeypatch):
    client, _, _, work, file, _ = preview
    cache = library.directory / 'cache'
    poster = cache / 'poster.jpg'
    thumb = cache / 'nfo-thumb.jpg'
    poster_bytes = picture(poster, 'red', 90, 160)
    thumb_bytes = picture(thumb, 'green')
    set_artwork(library, work['id'], poster, {str(file['id']): str(thumb)})
    def unexpected(*args, **kwargs):
        pytest.fail('A listing or existing NFO thumbnail must not run FFmpeg')
    monkeypatch.setattr('lumen.core.thumbnail', unexpected)
    result = client.get('/api/continue').json()['items'][0]
    assert result['resume']['thumbnail'] == f"/api/files/{file['id']}/thumbnail"
    assert result['cover'] != result['resume']['thumbnail']
    assert client.get(result['cover']).content == poster_bytes
    assert client.get(result['resume']['thumbnail']).content == thumb_bytes
    assert client.head(result['resume']['thumbnail']).status_code == 200
    assert str(library.directory) not in json.dumps(result)


def test_completed_episode_preview_uses_the_next_episode(library, preview):
    client, _, source, work, first, _ = preview
    second_path = library.directory / 'Show.S01E02.mp4'
    second_path.write_bytes(source.read_bytes())
    with library.db:
        library.db.execute("UPDATE works SET kind='series' WHERE id=?", (work['id'],))
        library.db.execute('UPDATE files SET season=1,episode=1,completed=1,position=4 WHERE id=?', (first['id'],))
        second = library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',
            (work['id'], str(second_path), 'episode-two', str(second_path.parent), 4, 1, 2)).lastrowid
    cache = library.directory / 'cache'
    poster = cache / 'series-poster.jpg'
    first_thumb = cache / 'episode-one.jpg'
    second_thumb = cache / 'episode-two-nfo.jpg'
    picture(poster, 'red', 90, 160)
    picture(first_thumb, 'blue')
    expected = picture(second_thumb, 'green')
    set_artwork(library, work['id'], poster, {str(first['id']): str(first_thumb), str(second): str(second_thumb)})
    resume = client.get('/api/continue').json()['items'][0]['resume']
    assert resume['file_id'] == second
    assert resume['thumbnail'] == f'/api/files/{second}/thumbnail'
    assert client.get(resume['thumbnail']).content == expected


def test_missing_frame_never_falls_back_to_poster_and_head_does_not_generate(library, preview, monkeypatch):
    client, _, _, work, file, clock = preview
    poster = library.directory / 'cache' / 'only-poster.jpg'
    poster_bytes = picture(poster, 'red', 90, 160)
    # Sidecars sometimes declare the very same poster as their thumbnail.
    set_artwork(library, work['id'], poster, {str(file['id']): str(poster)})
    attempts = []
    def fail(source, target, *args, **kwargs):
        attempts.append(Path(target))
        Path(target).write_bytes(b'partial-frame')
        raise RuntimeError('decode failed')
    monkeypatch.setattr('lumen.core.thumbnail', fail)
    route = f"/api/files/{file['id']}/thumbnail"
    assert client.head(route).status_code == 404
    assert attempts == []
    first = client.get(route)
    assert first.status_code == 404 and first.content != poster_bytes
    assert client.get(route).status_code == 404 and len(attempts) == 1
    assert all(not target.exists() for target in attempts)
    assert not (library.directory / 'cache' / (file['digest'] + '.jpg')).exists()
    clock[0] += 31
    assert client.get(route).status_code == 404 and len(attempts) == 2
    assert all(not target.exists() for target in attempts)


def test_missing_thumbnail_generates_and_reuses_an_atomic_video_frame(library, preview, monkeypatch):
    client, _, _, _, file, _ = preview
    from lumen.core import thumbnail
    attempts = []
    def capture(source, target, *args, **kwargs):
        attempts.append(Path(target))
        thumbnail(source, target, *args, **kwargs)
    monkeypatch.setattr('lumen.core.thumbnail', capture)
    route = f"/api/files/{file['id']}/thumbnail"
    target = library.directory / 'cache' / (file['digest'] + '.jpg')
    assert client.head(route).status_code == 404 and attempts == []
    response = client.get(route)
    assert response.status_code == 200 and response.content.startswith(b'\xff\xd8')
    assert target.read_bytes() == response.content
    assert client.get(route).content == response.content and len(attempts) == 1
    assert attempts[0] != target and not attempts[0].exists()
    image = QImage(str(target))
    assert image.width() == 480 and image.width() > image.height()


def test_thumbnail_auth_media_root_and_nfo_cache_boundaries(library, preview, tmp_path):
    client, _, _, work, file, _ = preview
    route = f"/api/files/{file['id']}/thumbnail"
    assert client.get(route, headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/files/999999/thumbnail').status_code == 404
    outside = tmp_path / 'private.jpg'
    picture(outside, 'red')
    set_artwork(library, work['id'], outside, {str(file['id']): str(outside)})
    assert client.get(route).status_code == 403
    assert str(outside) not in client.get(route).text
    with library.db:
        library.db.execute("UPDATE files SET root=? WHERE id=?", (str(tmp_path / 'other-root'), file['id']))
    assert client.get(route).status_code == 403


@pytest.mark.parametrize('digest', ['../../private', '/absolute', '..\\outside', 'space name'])
def test_digest_is_a_cache_identifier_not_a_path(library, preview, digest):
    client, _, _, _, file, _ = preview
    with library.db:
        library.db.execute('UPDATE files SET digest=? WHERE id=?', (digest, file['id']))
    assert client.get(f"/api/files/{file['id']}/thumbnail").status_code == 403


def test_frame_generation_is_bounded_and_does_not_block_video_seek(library, preview, monkeypatch):
    client, _, source, _, file, _ = preview
    entered = threading.Event()
    release = threading.Event()
    calls = []
    def capture(source, target, *args, **kwargs):
        calls.append(target)
        entered.set()
        assert release.wait(5), 'test must release the frame decoder'
        picture(Path(target), 'green')
    monkeypatch.setattr('lumen.core.thumbnail', capture)
    route = f"/api/files/{file['id']}/thumbnail"
    with ThreadPoolExecutor(max_workers=1) as workers:
        pending = workers.submit(client.get, route)
        try:
            assert entered.wait(3)
            assert client.get(route).status_code == 503
            assert client.head(route).status_code == 404
            stream = client.get(f"/api/files/{file['id']}/stream", headers={'Range': 'bytes=0-31'})
            assert stream.status_code == 206 and stream.content == source.read_bytes()[:32]
        finally:
            release.set()
        response = pending.result(timeout=3)
    assert response.status_code == 200 and len(calls) == 1
    assert client.get(route).content == response.content and len(calls) == 1


def test_frame_cpu_budget_wait_uses_the_deadline_and_always_releases(library, preview, monkeypatch):
    client, server, _, _, file, clock = preview
    monotonic = [0.0]
    # Replace only this module's clock, leaving socket/client timeouts untouched.
    monkeypatch.setattr('lumen.server.time', SimpleNamespace(monotonic=lambda: monotonic[0]))
    acquire = server.budget.acquire
    calls = []
    def expired_wait(cancelled, *, resource):
        assert resource == 'cpu' and not cancelled()
        monotonic[0] += 9
        acquire(cancelled, resource=resource)
    monkeypatch.setattr(server.budget, 'acquire', expired_wait)
    def capture(source, target, *args, **kwargs):
        calls.append(target)
        picture(Path(target), 'green')
        if len(calls) == 1:
            raise RuntimeError('decoder failed after acquiring a lease')
    monkeypatch.setattr('lumen.core.thumbnail', capture)
    route = f"/api/files/{file['id']}/thumbnail"
    target = library.directory / 'cache' / (file['digest'] + '.jpg')
    assert client.get(route).status_code == 503
    assert calls == [] and not target.exists()
    assert server.budget.active == 0 and not server.budget.waiters
    assert file['id'] not in server.thumbnail_failures

    monkeypatch.setattr(server.budget, 'acquire', acquire)
    # Resource contention is retryable immediately; only a real decode failure
    # below starts the unavailable-thumbnail cooldown.
    assert client.get(route).status_code == 404
    assert len(calls) == 1 and not target.exists()
    assert server.budget.active == 0 and not server.budget.leases
    clock[0] += 31
    assert client.get(route).status_code == 200
    assert target.is_file() and len(calls) == 2
    assert server.budget.active == 0 and not server.budget.leases
    assert not any(Path(path).exists() for path in calls)
