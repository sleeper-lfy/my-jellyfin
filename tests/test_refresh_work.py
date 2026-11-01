import os
from pathlib import Path
from types import SimpleNamespace
from lumen.core import WatchSession
from lumen.ui import MainWindow


def series_library(library, tmp_path):
    show = tmp_path/'Show'/'Season 1';show.mkdir(parents=True)
    for name in ['Show.S01E01.mp4', 'Show.S01E02.mp4', 'Show.S01E03.mp4']:
        (show/name).write_bytes(('video-' + name).encode())
    library.import_folder(tmp_path/'Show', 'series', fast=True)
    return library.query({'kinds': ['series']})[0]


def test_refresh_recovers_renames_imports_additions_reports_missing(library, tmp_path):
    work = series_library(library, tmp_path)
    original_third = work['files'][2]['path']
    (tmp_path/'Show'/'Season 1'/'Show.S01E02.mp4').unlink()
    renamed = tmp_path/'Show'/'Season 1'/'Show.S01E03.fixed.mp4'
    Path(original_third).rename(renamed)
    (tmp_path/'Show'/'Season 1'/'Show.S01E04.mp4').write_bytes(b'video-new-e4')
    (tmp_path/'Show'/'Season 2').mkdir();(tmp_path/'Show'/'Season 2'/'Show.S02E01.mp4').write_bytes(b'video-new-s2')
    result = library.refresh_work(work['id'])
    assert [Path(p).name for p in result['missing']] == ['Show.S01E02.mp4']
    assert result['renamed'] == [[original_third, str(renamed)]]
    assert result['imported'] == 2 and result['errors'] == []
    refreshed = library.work(work['id'])
    episodes = {Path(f['path']).name: f for f in refreshed['files']}
    assert set(episodes) == {'Show.S01E01.mp4', 'Show.S01E02.mp4', 'Show.S01E03.fixed.mp4', 'Show.S01E04.mp4', 'Show.S02E01.mp4'}
    assert (episodes['Show.S01E04.mp4']['season'], episodes['Show.S01E04.mp4']['episode']) == (1, 4)
    assert (episodes['Show.S02E01.mp4']['season'], episodes['Show.S02E01.mp4']['episode']) == (2, 1)
    assert episodes['Show.S01E03.fixed.mp4']['id'] == work['files'][2]['id']
    confirmed = library.remove_local_records(work['id'], [f['id'] for f in library.work(work['id'])['files'] if f['path'] in set(result['missing'])])
    assert confirmed == {'removed': 1, 'removed_work': False}
    refreshed = library.work(work['id'])
    assert {Path(f['path']).name for f in refreshed['files']} == {'Show.S01E01.mp4', 'Show.S01E03.fixed.mp4', 'Show.S01E04.mp4', 'Show.S02E01.mp4'}


def test_remove_local_records_keeps_files_drops_history_and_entry(library, tmp_path):
    work = series_library(library, tmp_path)
    first = work['files'][0]['id']
    WatchSession(library, first)
    with library.db:
        library.db.execute('INSERT INTO bookmarks VALUES (?,?,?,?,"",NULL,?)', ('b1', first, 12.0, '点', '2026-11-01'))
    result = library.remove_local_records(work['id'], [first])
    assert result == {'removed': 1, 'removed_work': False}
    assert Path(work['files'][0]['path']).is_file()
    assert not library.db.execute('SELECT 1 FROM sessions WHERE file_id=?', (first,)).fetchone()
    assert not library.db.execute('SELECT 1 FROM bookmarks WHERE file_id=?', (first,)).fetchone()
    remaining = library.work(work['id'])
    result = library.remove_local_records(work['id'], [f['id'] for f in remaining['files']])
    assert result['removed_work'] is True
    assert library.db.execute('SELECT 1 FROM works WHERE id=?', (work['id'],)).fetchone() is None


def test_discovered_work_survives_when_all_local_records_removed(library, tmp_path):
    from test_core import add_work
    work_id = add_work(library, 'Discovered series', kind='series')
    (tmp_path/'Show').mkdir();(tmp_path/'Show'/'Show.S01E01.mp4').write_bytes(b'video')
    library.import_folder(tmp_path/'Show', 'series', fast=True)
    library.merge_works(library.query({'kinds': ['series']})[0]['id'], work_id)
    with library.db:
        library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                           (work_id, 'catalog-json', 'Catalog', 'src-1', 'http://localhost/src-1', '2026-11-01', None, None))
    files = [f['id'] for f in library.work(work_id)['files']]
    result = library.remove_local_records(work_id, files)
    assert result['removed_work'] is False
    assert library.work(work_id)['files'] == [] and library.work(work_id)['sources']


def test_details_offer_scan_and_episode_removal(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMenu
    window = MainWindow(tmp_path/'refresh-ui')
    work = series_library(window.library, tmp_path)
    captured = []
    class RecordingMenu(QMenu):
        def exec(self, *args, **kwargs):
            captured.extend(action.text() for action in self.actions());return None
    monkeypatch.setattr('lumen.ui.QMenu', RecordingMenu)
    try:
        window.navigate('series');window.open_details(work['id'], fetch=False)
        detail = window.detail_page
        actions = [action.text() for action in detail.management_menu.actions()]
        assert '扫描本地文件变化…' in actions
        detail.episode_menu(detail.files.visualItemRect(detail.files.item(0)).center())
        assert any('移除此集的媒体库记录' in text for text in captured)
        assert any('第 1 季' in text for text in captured)
    finally:
        window.close()
