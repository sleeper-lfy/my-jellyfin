import json
import os
from pathlib import Path
import time

from lumen import background_worker as worker
from lumen.core import ImportCancelled, Library


def result(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_empty_watch_job_writes_safe_bounded_result_and_restores_environment(tmp_path, capsys, monkeypatch):
    directory = tmp_path / 'library'
    output = tmp_path / 'result.json'
    monkeypatch.setenv('LUMEN_BACKGROUND_WORKER', 'previous')
    monkeypatch.setenv('LUMEN_DATA_DIR', 'previous-directory')
    assert worker.main(['watch', '--data-dir', str(directory), '--result-file', str(output)]) == 0
    payload = result(output)
    assert payload['status'] == 'done' and payload['summary']['imported'] == 0
    assert payload['summary']['automation'] == {'completed': 0, 'pending': 0, 'retry': 0}
    assert json.loads(capsys.readouterr().out) == payload
    assert str(directory) not in output.read_text() and output.stat().st_size < worker.MAX_RESULT_BYTES
    assert os.environ['LUMEN_BACKGROUND_WORKER'] == 'previous'
    assert os.environ['LUMEN_DATA_DIR'] == 'previous-directory'
    assert not list(tmp_path.glob('result.json.*.tmp'))


def test_cancelled_marker_prevents_opening_the_library(tmp_path, monkeypatch):
    marker = tmp_path / 'cancel'
    marker.touch()
    output = tmp_path / 'result.json'
    def unexpected(*args, **kwargs):
        raise AssertionError('A pre-cancelled worker must not open the library')
    monkeypatch.setattr(worker, 'Library', unexpected)
    assert worker.run('watch', tmp_path / 'unopened', marker, output) == 2
    assert result(output)['status'] == 'cancelled'
    assert not (tmp_path / 'unopened').exists()


def test_watch_job_reuses_stability_state_and_imports_without_requiring_gui(library, tmp_path):
    folder = tmp_path / 'watched'
    folder.mkdir()
    source = folder / 'Watch.2024.mp4'
    source.write_bytes(b'indexed-before-media-analysis')
    os.utime(source, (10000, 10000))
    library.set_setting('watched_folders', [{'path': str(folder), 'kind': 'movie', 'settle_seconds': 0}])
    output = tmp_path / 'result.json'
    assert worker.run('watch', library.directory, result_file=output) == 0
    assert result(output)['summary']['waiting'] == 1
    assert worker.run('watch', library.directory, result_file=output) == 0
    assert result(output)['summary']['imported'] == 1
    assert library.db.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 1
    assert library.db.execute('SELECT pending FROM import_cache').fetchone()[0] == 1


def test_cancelled_media_keeps_pending_queue_for_the_next_worker(library, video_factory, tmp_path, monkeypatch):
    video = video_factory('Worker media.2024.mp4')
    library.import_folder(video.parent, 'movie', fast=True)
    marker = tmp_path / 'cancel'
    output = tmp_path / 'result.json'
    def cancelled_probe(path, cancelled):
        marker.touch()
        assert cancelled()
        raise ImportCancelled('stopped')
    monkeypatch.setattr('lumen.core.probe', cancelled_probe)
    assert worker.run('media', library.directory, marker, output) == 2
    assert result(output)['status'] == 'cancelled'
    assert library.db.execute('SELECT pending FROM import_cache').fetchone()[0] == 1
    assert library.db.execute("SELECT status FROM tasks WHERE kind='media'").fetchone()[0] == 'cancelled'


def test_recent_inspection_is_skipped_and_due_inspection_runs(library, tmp_path, monkeypatch):
    output = tmp_path / 'result.json'
    calls = []
    def inspect(self, progress=None, cancelled=None):
        calls.append(cancelled)
        assert not cancelled()
        progress(0, 1, 'safe checkpoint')
        return {'scanned': 1, 'offline': ['/private/root'], 'missing': 0, 'errors': 0}
    monkeypatch.setattr(Library, 'inspect_batch', inspect)
    library.set_setting('inspection', {'last': time.time()})
    assert worker.run('inspect', library.directory, result_file=output) == 0
    assert result(output)['summary']['skipped'] and calls == []
    library.set_setting('inspection', {'last': 1})
    assert worker.run('inspect', library.directory, result_file=output) == 0
    assert result(output)['summary']['scanned'] == 1 and result(output)['summary']['offline'] == 1
    assert len(calls) == 1 and '/private/root' not in output.read_text()


def test_discovery_refreshes_only_due_enabled_auto_sources(library, tmp_path, monkeypatch):
    output = tmp_path / 'result.json'
    refreshed = []
    class FakePlugins:
        def __init__(self, library):
            self.library = library
        def installed(self):
            defaults = {'enabled': True, 'auto_refresh': True, 'interval_hours': 1}
            return [
                {'id': 'due', 'capabilities': ['discover'], 'config': defaults},
                {'id': 'recent', 'capabilities': ['discover'], 'config': {**defaults, 'last_attempt': time.time()}},
                {'id': 'disabled', 'capabilities': ['discover'], 'config': {**defaults, 'enabled': False}},
                {'id': 'manual', 'capabilities': ['discover'], 'config': {**defaults, 'auto_refresh': False}},
                {'id': 'search-only', 'capabilities': ['search'], 'config': defaults},
            ]
        def refresh(self, identifier):
            assert self.library.cancelled() is False
            refreshed.append(identifier)
    monkeypatch.setattr('lumen.plugins.Plugins', FakePlugins)
    assert worker.run('discovery', library.directory, result_file=output) == 0
    assert refreshed == ['due']
    assert result(output)['summary'] == {'refreshed': 1, 'due': 1, 'errors': 0}


def test_worker_reports_failure_without_leaking_exception_paths_or_keys(library, tmp_path, capsys, monkeypatch):
    output = tmp_path / 'result.json'
    secret_message = '/private/media/movie.mp4 https://secret.invalid/?token=abc123'
    def fail(*args, **kwargs):
        raise OSError(secret_message)
    monkeypatch.setattr(worker, '_perform', fail)
    assert worker.run('watch', library.directory, result_file=output) == 1
    payload = result(output)
    assert payload['status'] == 'failed' and payload['error_type'] == 'OSError'
    assert secret_message not in capsys.readouterr().out
    assert secret_message not in output.read_text()
    assert secret_message not in (library.directory / 'background-worker.log').read_text()


def test_result_file_works_without_standard_output(library, tmp_path, monkeypatch):
    output = tmp_path / 'result.json'
    monkeypatch.setattr(worker.sys, 'stdout', None)
    assert worker.run('media', library.directory, result_file=output) == 0
    assert result(output)['status'] == 'done'
