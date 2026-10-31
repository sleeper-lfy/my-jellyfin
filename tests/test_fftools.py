import hashlib
import io
import os
import zipfile
import httpx
import pytest
from lumen import core, fftools


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    data = tmp_path/'data';data.mkdir()
    monkeypatch.setenv('LUMEN_DATA_DIR', str(data))
    core.set_tool_directory(None)
    yield data
    core.set_tool_directory(None)


def test_tool_lookup_prefers_configured_then_path_then_downloaded(isolated_data, monkeypatch):
    configured = isolated_data/'tools'; configured.mkdir()
    (configured/'ffmpeg.exe').write_bytes(b'MZ-configured')
    downloaded = isolated_data/'ffmpeg'; downloaded.mkdir()
    (downloaded/'ffmpeg.exe').write_bytes(b'MZ-downloaded')
    monkeypatch.setattr(core.shutil, 'which', lambda name: str(isolated_data/'path-ffmpeg.exe'))
    core.set_tool_directory(str(configured))
    assert core.tool('ffmpeg') == str(configured/'ffmpeg.exe')
    (configured/'ffmpeg.exe').unlink()
    assert core.tool('ffmpeg') == str(isolated_data/'path-ffmpeg.exe')
    monkeypatch.setattr(core.shutil, 'which', lambda name: None)
    assert core.tool('ffmpeg') == str(downloaded/'ffmpeg.exe')
    (downloaded/'ffmpeg.exe').unlink()
    assert core.tool('ffmpeg') is None


def test_enrich_retry_keeps_pending_when_ffmpeg_missing(library, video_factory, monkeypatch):
    source = video_factory('Pending.mp4', 'blue', 2)
    library.import_folder(source.parent, 'movie', fast=True)
    assert library.db.execute('SELECT pending FROM import_cache').fetchone()[0] == 1
    monkeypatch.setattr(core, 'tool', lambda name: None)
    result = library.enrich_pending()
    assert result['needs_ffmpeg'] is True and result['completed'] == 0
    assert library.db.execute('SELECT pending FROM import_cache').fetchone()[0] == 1
    assert not library.db.execute("SELECT 1 FROM tasks WHERE kind='media' AND status='failed'").fetchone()


def make_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as bundle:
        for name in ('ffmpeg.exe', 'ffprobe.exe'):
            bundle.writestr(f'ffmpeg-9.0.2-essentials_build/bin/{name}', b'MZ' + name.encode() + b'x' * 4096)
    return buffer.getvalue()


def test_ensure_survives_bad_pin_then_extracts_verified_tools(isolated_data, monkeypatch):
    payload = make_zip()
    good = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(core, 'tool', lambda name: None)
    monkeypatch.setattr(fftools, 'SOURCES', (
        {'url': 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip', 'sha256': '0' * 64},
        {'url': 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', 'sha256': None},
    ))
    served = []
    calls = []
    monkeypatch.setattr(fftools, 'verify_runtime', lambda extracted: calls.append(sorted(extracted)))
    def fetcher(url):
        served.append(url);return httpx.Response(200, content=payload)
    result = fftools.ensure(progress=lambda *args: None, cancelled=lambda: False, fetcher=fetcher)
    assert served[0].endswith('ffmpeg-9.0.2-essentials_build.zip') and served[1].endswith('ffmpeg-release-essentials.zip')
    assert result['ffmpeg'] == str(isolated_data/'ffmpeg'/'ffmpeg.exe')
    assert (isolated_data/'ffmpeg'/'ffmpeg.exe').is_file() and (isolated_data/'ffmpeg'/'ffprobe.exe').is_file()
    assert calls and calls[0] == ['ffmpeg.exe', 'ffprobe.exe']
    source = (isolated_data/'ffmpeg'/'source.json').read_text(encoding='utf-8')
    assert good in source and 'ffmpeg-release-essentials.zip' in source
    assert not (isolated_data/'ffmpeg'/'ffmpeg-download.zip.part').exists()


def test_ensure_raises_when_every_source_fails(isolated_data, monkeypatch):
    payload = make_zip()
    monkeypatch.setattr(core, 'tool', lambda name: None)
    monkeypatch.setattr(fftools, 'SOURCES', (
        {'url': 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip', 'sha256': '0' * 64},
        {'url': 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', 'sha256': '1' * 64},
    ))
    with pytest.raises(ValueError, match='FFmpeg 组件下载失败'):
        fftools.ensure(progress=lambda *args: None, cancelled=lambda: False,
                       fetcher=lambda url: httpx.Response(200, content=payload))
    assert not (isolated_data/'ffmpeg'/'ffmpeg.exe').exists()
