from pathlib import Path
from unittest.mock import Mock
from lumen.import_ui import ImportDialog
from lumen.plugins import Plugins
from lumen.ui import MainWindow
from test_gallery_downloads import manager_for


def recorder(window):
    window.run_job = Mock()


def inline(window):
    window.run_job = Mock(side_effect=lambda title, function, callback=None: function(window.library, lambda *args: None))


def test_auto_scrape_takes_first_exact_match_then_first_candidate(qapp, tmp_path, monkeypatch):
    window = MainWindow(tmp_path/'first-match')
    manager_for(window.library)
    window.library.set_setting('partition:movie', {'plugin': 'catalog-json'})
    ids = {}
    responses = {}
    monkeypatch.setattr(Plugins, 'run', lambda self, plugin_id, operation, query=None, **kw: responses[query])
    try:
        for name in ['Alpha', 'Beta', 'Gamma', 'Delta']:
            folder = tmp_path/name.lower(); folder.mkdir()
            (folder/f'{name}.2024.mp4').write_bytes(('video-' + name).encode())
            window.library.import_folder(folder, 'movie', fast=True)
            ids[name] = window.library.query({'kinds': ['movie'], 'folder': str(folder.resolve())})[0]['id']
        responses.update({
            'Alpha': [{'id': 'old', 'title': 'Alpha', 'year': 2019, 'kind': 'movie', 'url': 'http://localhost/old'},
                      {'id': 'exact', 'title': 'Alpha', 'year': 2024, 'kind': 'movie', 'url': 'http://localhost/exact'}],
            'Beta': [{'id': 'b1', 'title': 'Beta', 'year': 2024, 'kind': 'movie', 'url': 'http://localhost/b1'},
                     {'id': 'b2', 'title': 'Beta', 'year': 2024, 'kind': 'movie', 'url': 'http://localhost/b2'}],
            'Gamma': [{'id': 'fuzzy', 'title': 'Gamma Reloaded', 'kind': 'movie', 'url': 'http://localhost/fuzzy'}],
            'Delta': [],
        })
        for name in ['Alpha', 'Beta', 'Gamma', 'Delta']:
            inline(window)
            window.auto_scrape_import(str(tmp_path/name.lower()), 'movie')
            assert window.run_job.called
        # Exact title+year match wins even behind an earlier wrong-year candidate.
        assert window.library.work(ids['Alpha'])['sources'][0]['source_id'] == 'exact'
        # Ambiguous titles default to the first search result instead of failing.
        assert window.library.work(ids['Beta'])['sources'][0]['source_id'] == 'b1'
        # Without an exact match the first candidate is used.
        assert window.library.work(ids['Gamma'])['sources'][0]['source_id'] == 'fuzzy'
        pending = window.library.db.execute("SELECT error FROM tasks WHERE kind='match' AND status='pending'").fetchall()
        assert len(pending) == 1 and '未找到候选' in pending[0][0]
    finally:
        window.close()


def test_explicit_no_scraper_ignores_partition_rule(qapp, tmp_path):
    window = MainWindow(tmp_path/'no-scrape')
    manager_for(window.library)
    recorder(window)
    window.library.set_setting('partition:movie', {'plugin': 'catalog-json'})
    try:
        window.auto_scrape_import(str(tmp_path), 'movie', plugin_id='')
        window.run_job.assert_not_called()
    finally:
        window.close()


def test_destination_moves_files_even_without_scraper(qapp, tmp_path):
    window = MainWindow(tmp_path/'move-only')
    manager_for(window.library)
    folder = tmp_path/'source'; folder.mkdir()
    video = folder/'Solo.2024.mp4'; video.write_bytes(b'video')
    video.with_suffix('.nfo').write_text('<movie><title>Solo</title></movie>', encoding='utf-8')
    window.library.import_folder(folder, 'movie', fast=True)
    work_id = window.library.query({'kinds': ['movie']})[0]['id']
    destination = tmp_path/'organized'; destination.mkdir()
    inline(window)
    try:
        window.auto_scrape_import(str(folder), 'movie', plugin_id='', destination=str(destination))
        moved = window.library.work(work_id)['files'][0]
        target = Path(moved['path'])
        assert not video.exists() and target.is_file()
        assert target.is_relative_to(destination) and target.with_suffix('.nfo').is_file()
    finally:
        window.close()


def test_start_import_queues_batch_folders_with_same_options(qapp, tmp_path):
    window = MainWindow(tmp_path/'batch')
    recorder(window)
    try:
        window.start_import(tmp_path/'one', 'movie', 'catalog-json', 'D:\\Movies', batch=[tmp_path/'two', tmp_path/'three'])
        titles = [call.args[0] for call in window.run_job.call_args_list]
        assert len(titles) == 3 and all(title.startswith('快速导入') for title in titles)
    finally:
        window.close()


def test_import_dialog_defaults_batch_note_and_fans_lock(qapp, tmp_path):
    window = MainWindow(tmp_path/'dialog')
    manager_for(window.library)
    window.library.set_setting('partition:movie', {'plugin': 'catalog-json', 'destination': 'D:\\Movies'})
    try:
        dialog = ImportDialog(window)
        dialog.kind.setCurrentIndex(dialog.kind.findData('movie')); dialog.sync_kind()
        assert dialog.scraper.currentData() == 'catalog-json' and dialog.destination.text() == 'D:\\Movies'
        dialog.pending = ['a', 'b']; dialog.sync_kind()
        assert '3 个文件夹' in dialog.message.text()
        dialog.kind.setCurrentIndex(dialog.kind.findData('fans')); dialog.sync_kind()
        assert not dialog.scraper.isEnabled() and not dialog.destination.isEnabled()
        assert dialog.scraper.currentData() in (None, '') and dialog.destination.text() == ''
        assert '第一层作者' in dialog.message.text()
        dialog.scraper.setCurrentIndex(dialog.scraper.findData('catalog-json'))
        dialog.refresh_scrapers()
        assert dialog.scraper.currentData() == 'catalog-json'
        dialog.close()
    finally:
        window.close()
