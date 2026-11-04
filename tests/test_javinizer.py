import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from lumen import javinizer as engine
from lumen.core import ImportCancelled, Library
from lumen.plugins import Plugins
from test_core import add_work


def raw(source='r18dev', **changes):
    hosts = {'r18dev': 'r18.dev', 'libredmm': 'www.libredmm.com', 'javbus': 'www.javbus.com'}
    return {'source': source, 'source_url': f'https://{hosts[source]}/detail/IPX-535',
            'id': 'IPX-535', 'content_id': 'ipx00535', 'title': 'Source title',
            'original_title': 'Original title', 'description': 'Description',
            'release_date': '2020-09-13T00:00:00Z', 'rating': {'score': 8.2},
            'poster_url': 'https://awsimgsrc.dmm.com/dig/poster.jpg',
            'screenshot_urls': ['https://pics.dmm.co.jp/still.jpg'],
            'genres': ['Drama'], 'actresses': [{'japanese_name': 'Actor', 'first_name': 'First',
                'last_name': 'Last', 'dmm_id': 123, 'thumb_url': 'https://pics.dmm.co.jp/actor.jpg'}], **changes}


@pytest.fixture
def enabled(library, monkeypatch, tmp_path):
    executable = tmp_path / 'engine' / 'javinizer.exe'
    executable.parent.mkdir()
    engine.save_settings(library, {'enabled': True})
    monkeypatch.setattr(engine, 'verified_executable', lambda *_args: executable)
    return Plugins(library)


@pytest.mark.parametrize('value,expected', [('ipx-00535-C.mp4', 'IPX-535'),
    ('[group] IPX_535 1080p', 'IPX-535'), ('ipx00535', 'IPX-535'),
    ('FC2 PPV 1234567.mkv', 'FC2-PPV-1234567'), ('300MIUM-123', '300MIUM-123'),
    ('T28-123', 'T28-123'), ('123456_789', '123456-789')])
def test_filename_code(value, expected):
    assert engine.movie_code(value) == expected


@pytest.mark.parametrize('value', ['Movie title', 'IPX-535 IPX-536', '--help', '', 'FC2-PPV-1234567 ABC-123'])
def test_ambiguous_or_non_id_input_is_rejected(value):
    with pytest.raises(ValueError):
        engine.movie_code(value)


def test_mapping_rejects_wrong_movie_and_keeps_source_score():
    record = engine.metadata(raw(), 'r18dev', 'IPX-535')
    assert record['external_ids'] == {'jav': 'IPX-535', 'dmm': 'ipx00535'}
    assert record['year'] == 2020 and record['rating'] == 8.2
    assert record['actors'][0]['name'] == 'Actor' and record['actors'][0]['aliases'] == ['First Last']
    assert record['stills'] and record['poster']
    with pytest.raises(ValueError, match='番号'):
        engine.metadata(raw(id='IPX-536'), 'r18dev', 'IPX-535')
    with pytest.raises(ValueError, match='来源地址'):
        engine.metadata(raw(source_url='http://localhost/film'), 'r18dev', 'IPX-535')
    record = engine.metadata(raw(poster_url='http://localhost/p.jpg', cover_url='file:///etc/secret',
                                  screenshot_urls=['https://unlisted.test/s.jpg']), 'r18dev', 'IPX-535')
    assert not record['poster'] and record['stills'] == []


def test_dmm_cdn_referrer_and_undeclared_rating_scale(library):
    engine.save_settings(library, {})
    plugin = engine.provider(library)
    assert Plugins(library)._request_headers(plugin, 'https://awsimgsrc.dmm.com/dig/poster.jpg')['Referer'] == 'https://www.dmm.co.jp/'
    assert engine.metadata(raw('libredmm', rating={'score': 4.4}), 'libredmm', 'IPX-535')['rating'] is None


def test_sequential_fallback_cache_and_cooldown(library, enabled, monkeypatch):
    calls = []
    def query(_lib, _executable, source, code, config, cancelled):
        calls.append(source)
        if source == 'r18dev':
            raise engine.SourceError(source, {'kind': 'blocked', 'status_code': 403})
        return engine.metadata(raw(source), source, code)
    monkeypatch.setattr(engine, 'query_source', query)
    first = enabled.run(engine.ENGINE_ID, 'search', query='IPX-535')
    assert calls == ['r18dev', 'libredmm'] and first[0]['javinizer_source'] == 'libredmm'
    assert enabled.run(engine.ENGINE_ID, 'search', query='ipx00535') == first
    assert calls == ['r18dev', 'libredmm']
    errors = library.db.execute("SELECT payload,error FROM tasks WHERE kind='scrape-source'").fetchall()
    assert len(errors) == 1 and 'r18.dev' in errors[0]['error'] and '403' in errors[0]['error']
    assert engine.clear_cache(library)['removed'] == 1
    enabled.run(engine.ENGINE_ID, 'search', query='IPX-535')
    assert calls == ['r18dev', 'libredmm', 'r18dev', 'libredmm']


def test_cache_ttl_and_bound(library, enabled, monkeypatch):
    record = engine.metadata(raw(), 'r18dev', 'IPX-535')
    key = engine.CACHE_PREFIX + 'r18dev:IPX-535'
    library.set_setting(key, {'at': time.time() - 8 * 86400, 'record': record})
    calls = []
    monkeypatch.setattr(engine, 'query_source', lambda *args: calls.append(args[2]) or record)
    enabled.run(engine.ENGINE_ID, 'search', query='IPX-535')
    assert calls == ['r18dev']
    monkeypatch.setattr(engine, 'MAX_CACHE_ENTRIES', 2)
    for code in ['IPX-536', 'IPX-537']:
        engine._cache_result(library, 'r18dev', code, {**record, 'id': code})
    keys = [row[0] for row in library.db.execute('SELECT key FROM settings WHERE key GLOB ?', (engine.CACHE_PREFIX + '*',))]
    assert len(keys) == 2 and key not in keys


def test_all_errors_are_not_reported_as_no_results(library, enabled, monkeypatch):
    def fail(_lib, _exe, source, *_args):
        raise engine.SourceError(source, {'kind': 'auth', 'status_code': 401})
    monkeypatch.setattr(engine, 'query_source', fail)
    with pytest.raises(ValueError, match='401'):
        enabled.run(engine.ENGINE_ID, 'search', query='IPX-535')
    assert library.db.execute("SELECT count(*) FROM tasks WHERE kind='scrape' AND status='failed'").fetchone()[0] == 1
    def not_found(_lib, _exe, source, *_args):
        raise engine.SourceError(source, {'kind': 'not_found', 'status_code': 404})
    monkeypatch.setattr(engine, 'query_source', not_found)
    engine.clear_cache(library)
    assert enabled.run(engine.ENGINE_ID, 'search', query='IPX-535') == []


def test_query_envelope_config_and_no_video_operations(library, enabled, monkeypatch, tmp_path):
    seen = []
    def process(command, directory, timeout, cancelled):
        config = json.loads(Path(command[2]).read_text(encoding='utf-8'))
        seen.append((command, config))
        assert config['scrapers']['browser']['enabled'] is False
        assert config['scrapers']['flaresolverr']['enabled'] is False
        assert not config['scrapers']['dmm']['enabled']
        assert sum(bool(config['scrapers'][s]['enabled']) for s in engine.ALL_SCRAPERS) == 1
        assert config['scrapers']['proxy']['profiles']['lumen']['url'] == 'http://127.0.0.1:7890'
        return 0, json.dumps(raw())
    library.set_setting('proxy', 'http://127.0.0.1:7890')
    monkeypatch.setattr(engine, 'run_process', process)
    records = enabled.run(engine.ENGINE_ID, 'search', query='IPX-535')
    assert len(records) == 1
    command = seen[0][0]
    assert command[3:] == ['scrape', 'IPX-535', '--scrapers', 'r18dev', '--output', 'json', '--no-browser']
    assert not list((tmp_path / 'engine').glob('query-*'))


def test_native_provider_is_opt_in_and_cannot_be_installed_from_script(library, tmp_path):
    manager = Plugins(library)
    assert manager.installed() == []
    engine.save_settings(library, {'enabled': False})
    assert manager.installed()[0]['engine'] == engine.ENGINE_ID
    with pytest.raises(ValueError, match='未启用'):
        manager.run(engine.ENGINE_ID, 'search', query='IPX-535')
    folder = tmp_path / 'fake'; folder.mkdir()
    (folder / 'manifest.json').write_text(json.dumps({'id': engine.ENGINE_ID}), encoding='utf-8')
    with pytest.raises(ValueError, match='保留'):
        manager.install(folder)
    manager.uninstall(engine.ENGINE_ID)
    assert manager.installed() == []


def test_failed_component_install_preserves_previous_binary_and_removes_partial(library, tmp_path, monkeypatch):
    monkeypatch.setattr(engine.sys, 'platform', 'win32')
    target = engine.executable_path(library)
    target.parent.mkdir(parents=True)
    target.write_bytes(b'old-component')
    bad = tmp_path / 'untrusted.exe'; bad.write_bytes(b'untrusted')
    with pytest.raises(ValueError, match='SHA-256'):
        engine.install(library, local_file=bad)
    assert target.read_bytes() == b'old-component' and not list(target.parent.glob('*.part'))
    assert not engine.settings(library)['enabled']


def test_cancelled_install_does_not_enable_component(library, tmp_path, monkeypatch):
    monkeypatch.setattr(engine.sys, 'platform', 'win32')
    with pytest.raises(ImportCancelled):
        engine.install(library, cancelled=lambda: True)
    assert not engine.executable_path(library).exists()


def test_streaming_download_verifies_then_atomically_installs(library, monkeypatch):
    import hashlib
    import httpx
    data = b'MZverified-published-component'
    monkeypatch.setattr(engine.sys, 'platform', 'win32')
    monkeypatch.setattr(engine, 'BINARY_SIZE', len(data))
    monkeypatch.setattr(engine, 'SHA256', hashlib.sha256(data).hexdigest())
    requests = []
    def response(request):
        requests.append(request)
        if request.url.host == 'github.com':
            return httpx.Response(302, headers={'location': 'https://release-assets.githubusercontent.com/asset'})
        return httpx.Response(200, content=data)
    real_client = httpx.Client
    monkeypatch.setattr(engine.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(response)))
    result = engine.install(library)
    assert Path(result['path']).read_bytes() == data
    assert engine.settings(library)['enabled'] and len(requests) == 2
    assert engine.verified_executable(library) == Path(result['path'])


def test_component_redirect_cannot_leave_official_release_hosts():
    import httpx
    transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={'location': 'https://untrusted.test/asset'}))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ValueError, match='GitHub'):
            engine._download_response(client)


def test_child_environment_cannot_select_external_server_or_database(monkeypatch, tmp_path):
    monkeypatch.setenv('JAVINIZER_CONFIG', 'untrusted.yaml')
    monkeypatch.setenv('JAVINIZER_DB', '/other/database')
    monkeypatch.setenv('JAVINIZER_E2E_SCRAPERS', 'true')
    monkeypatch.setenv('HTTPS_PROXY', 'http://unwanted:1234')
    env = engine._child_environment(tmp_path)
    assert 'JAVINIZER_CONFIG' not in env and 'JAVINIZER_DB' not in env
    assert 'JAVINIZER_E2E_SCRAPERS' not in env and 'HTTPS_PROXY' not in env
    assert env['JAVINIZER_HOME'] == str(tmp_path) and env['GOMEMLIMIT'] == '96MiB'


@pytest.mark.parametrize('stop', ['cancel', 'timeout'])
def test_stopping_engine_kills_its_descendant_process(tmp_path, stop):
    child_pid = tmp_path / 'child.pid'
    script = tmp_path / 'process_tree.py'
    script.write_text("import subprocess, sys, time\nfrom pathlib import Path\n"
                      "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                      f"Path({str(child_pid)!r}).write_text(str(p.pid))\n"
                      "time.sleep(60)\n", encoding='utf-8')
    started = time.monotonic()
    cancelled = lambda: child_pid.exists() if stop == 'cancel' else False
    with pytest.raises(ImportCancelled if stop == 'cancel' else TimeoutError):
        engine.run_process([sys.executable, str(script)], tmp_path, 2, cancelled)
    assert time.monotonic() - started < 5
    if child_pid.exists():
        pid = int(child_pid.read_text())
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x100000, False, pid)
            if handle:
                try:
                    assert kernel.WaitForSingleObject(handle, 3000) == 0
                finally:
                    kernel.CloseHandle(handle)
        else:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)


def test_process_output_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'MAX_OUTPUT', 100)
    with pytest.raises(ValueError, match='输出'):
        engine.run_process([sys.executable, '-c', "print('x'*1000)"], tmp_path, 3)


def test_queries_are_serial_even_when_multiple_jobs_are_allowed(library, enabled, monkeypatch):
    entered = threading.Event(); release = threading.Event(); order = []
    def query(lib, executable, source, code, config, cancelled):
        order.append(code); entered.set()
        assert release.wait(3)
        return engine.metadata(raw(id=code), source, code)
    monkeypatch.setattr(engine, 'query_source', query)
    failures = []
    def run():
        lib = Library(library.directory)
        try:
            engine.lookup(lib, 'IPX-535')
        except BaseException as error:
            failures.append(error)
        finally:
            lib.close()
    thread = threading.Thread(target=run); thread.start()
    try:
        assert entered.wait(3)
        with pytest.raises(ImportCancelled):
            engine.lookup(library, 'IPX-536', cancelled=lambda: True)
        assert order == ['IPX-535']
    finally:
        release.set(); thread.join(4)
    assert not failures and not thread.is_alive()


def test_image_failure_preserves_metadata_locks_rating_and_files(library, enabled, monkeypatch):
    work_id = add_work(library, 'Local title', metadata={'overview': 'Keep'})
    library.edit_metadata(work_id, {'title': 'Locked title', 'overview': 'Keep'}, ['title', 'overview'])
    with library.db:
        library.db.execute('UPDATE works SET rating=9 WHERE id=?', (work_id,))
    def fail(self, plugin, url, image=False):
        assert not self.library.db.in_transaction
        raise ValueError('HTTP 403 from pics.dmm.co.jp')
    monkeypatch.setattr(Plugins, 'fetch', fail)
    enabled.merge(engine.ENGINE_ID, engine.metadata(raw(), 'r18dev', 'IPX-535'), work_id, replace_nfo=True)
    work = library.work(work_id)
    assert work['title'] == 'Locked title' and work['metadata']['overview'] == 'Keep'
    assert work['rating'] == 9 and work['sources'][0]['rating'] == 8.2
    assert work['metadata']['actors'][0]['name'] == 'Actor'
    assert library.db.execute("SELECT count(*) FROM tasks WHERE kind='image' AND status='failed'").fetchone()[0] == 3


def test_image_fetch_does_not_overwrite_concurrent_edits(qapp, library, enabled, monkeypatch):
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QImage, QColor
    picture = QImage(20, 30, QImage.Format.Format_RGB32); picture.fill(QColor('red'))
    data = QByteArray(); buffer = QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly); picture.save(buffer, 'PNG')
    work_id = add_work(library, 'Original')
    def fetch(self, plugin, url, image=False):
        other = Library(library.directory)
        try:
            other.edit_metadata(work_id, {'overview': 'Edited during download'}, ['overview'])
        finally:
            other.close()
        return bytes(data), 'image/png'
    monkeypatch.setattr(Plugins, 'fetch', fetch)
    enabled.merge(engine.ENGINE_ID, engine.metadata(raw(), 'r18dev', 'IPX-535'), work_id, replace_nfo=True)
    work = library.work(work_id)
    assert work['metadata']['overview'] == 'Edited during download'
    assert Path(work['thumbnail']).is_file() and work['metadata']['actors'][0]['photo_cache']
    assert work['metadata']['stills_cache']
