from pathlib import Path
from lumen import core


def series_library(library, tmp_path, name='Show', count=3):
    show = tmp_path/name/'Season 1';show.mkdir(parents=True)
    for index in range(1, count+1):
        (show/f'{name}.S01E{index:02}.mp4').write_bytes((f'video-{name}-{index}').encode())
    library.import_folder(tmp_path/name, 'series', fast=True)
    return library.query({'kinds': ['series']})[-1]


def test_inspection_reports_missing_without_removing(library, tmp_path):
    work = series_library(library, tmp_path)
    (tmp_path/'Show'/'Season 1'/'Show.S01E02.mp4').unlink()
    findings = library.inspect_batch(limit=10, seconds=30)
    assert findings['scanned'] == 1 and findings['missing'] == 1 and findings['renamed'] == 0
    assert len(library.work(work['id'])['files']) == 3
    task = library.db.execute('SELECT status,payload FROM tasks WHERE id=?', ('inspect-' + str(work['id']),)).fetchone()
    assert task[0] == 'pending' and 'Show.S01E02.mp4' in task[1]
    assert library.setting('inspection')['last'] > 0


def test_inspection_recovers_rename_and_imports_addition(library, tmp_path):
    work = series_library(library, tmp_path)
    old = work['files'][2]['path']
    new = Path(old).with_name('Show.S01E03.fixed.mp4');Path(old).rename(new)
    (tmp_path/'Show'/'Season 2').mkdir();(tmp_path/'Show'/'Season 2'/'Show.S02E01.mp4').write_bytes(b'video-s2')
    findings = library.inspect_batch(limit=10, seconds=30)
    assert findings['renamed'] == 1 and findings['imported'] == 1 and findings['missing'] == 0
    episodes = {Path(f['path']).name: f for f in library.work(work['id'])['files']}
    assert 'Show.S01E03.fixed.mp4' in episodes
    assert (episodes['Show.S02E01.mp4']['season'], episodes['Show.S02E01.mp4']['episode']) == (2, 1)


def test_inspection_cursor_rotates_in_batches(library, tmp_path):
    for name in ['ShowA', 'ShowB', 'ShowC']:
        series_library(library, tmp_path, name=name, count=1)
    findings = library.inspect_batch(limit=2, seconds=30)
    assert findings['scanned'] == 2
    assert library.setting('inspection')['cursor'] == 2
    (tmp_path/'ShowC'/'Season 1'/'ShowC.S01E01.mp4').unlink()
    findings = library.inspect_batch(limit=2, seconds=30)
    assert findings['scanned'] == 1 and findings['missing'] == 1
    assert library.setting('inspection')['cursor'] == 0


def test_inspection_skips_offline_roots_until_expiry(library, tmp_path, monkeypatch):
    work = series_library(library, tmp_path)
    (tmp_path/'Show'/'Season 1'/'Show.S01E01.mp4').unlink()
    monkeypatch.setattr(core, 'root_online', lambda root: False)
    findings = library.inspect_batch(limit=10, seconds=30)
    assert findings['offline'] and findings['scanned'] == 0 and findings['missing'] == 0
    assert len(library.work(work['id'])['files']) == 3
    state = library.setting('inspection')
    state['offline'] = {root: 0 for root in state['offline']}
    library.set_setting('inspection', state)
    monkeypatch.setattr(core, 'root_online', lambda root: True)
    findings = library.inspect_batch(limit=10, seconds=30)
    assert findings['missing'] == 1 and findings['scanned'] == 1


def test_confirming_removal_closes_inspection_task(library, tmp_path):
    work = series_library(library, tmp_path)
    (tmp_path/'Show'/'Season 1'/'Show.S01E01.mp4').unlink()
    library.inspect_batch(limit=10, seconds=30)
    identifier = 'inspect-' + str(work['id'])
    assert library.db.execute('SELECT status FROM tasks WHERE id=?', (identifier,)).fetchone()[0] == 'pending'
    victim = next(f['id'] for f in library.work(work['id'])['files'] if f['path'].endswith('Show.S01E01.mp4'))
    library.remove_local_records(work['id'], [victim])
    assert library.db.execute('SELECT status FROM tasks WHERE id=?', (identifier,)).fetchone()[0] == 'done'
