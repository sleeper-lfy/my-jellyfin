import sqlite3
from pathlib import Path
import pytest
from lumen.core import Library
from lumen import migrations
from lumen.backup import restore_database


@pytest.mark.parametrize('tag', ['v0.4.9', 'v0.4.10'])
def test_real_historical_initializers_upgrade_without_losing_data(tmp_path, tag):
    import hashlib
    import json
    fixtures = Path(__file__).parent / 'fixtures/schema'
    path = fixtures / (tag + '.sql')
    provenance = json.loads((fixtures / 'provenance.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == provenance[tag]['fixture_sha256']
    directory = tmp_path / tag
    directory.mkdir()
    with sqlite3.connect(directory / 'library.sqlite') as db:
        db.executescript(path.read_text(encoding='utf-8'))
    lib = Library(directory)
    assert lib.work(1)['rating'] == 8 and lib.work(1)['favorite'] == 1
    assert lib.work(1)['files'][0]['position'] == 35
    assert lib.setting('queue') == [1]
    assert lib.db.execute('SELECT watched FROM sessions').fetchone()[0] == 35
    assert lib.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    lib.close()


def legacy(directory, version=0):
    directory.mkdir()
    db = sqlite3.connect(directory / 'library.sqlite')
    migrations.baseline(db)
    db.execute("INSERT INTO works(identity,kind,title,favorite,added) VALUES ('legacy','movie','保留资料',1,'2026')")
    db.execute(f'PRAGMA user_version={version}')
    db.commit()
    db.close()


@pytest.mark.parametrize('version', [0, 1])
def test_ordered_upgrade_backups_and_reopen(tmp_path, version):
    directory = tmp_path / 'old'
    legacy(directory, version)
    lib = Library(directory)
    assert lib.db.execute('PRAGMA user_version').fetchone()[0] == migrations.SCHEMA_VERSION
    assert lib.work(1)['favorite'] == lib.work(1)['liked'] == 1
    backups = list((directory / 'backups').glob('*.sqlite'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute('PRAGMA user_version').fetchone()[0] == version
        assert 'liked' not in {row[1] for row in backup.execute('PRAGMA table_info(works)')}
    lib.close()
    lib = Library(directory)
    lib.close()
    assert list((directory / 'backups').glob('*.sqlite')) == backups


def test_failure_rolls_back_ddl_data_and_version_then_retries(tmp_path, monkeypatch):
    directory = tmp_path / 'old'
    legacy(directory)
    original = migrations.MIGRATIONS[2]
    def fail(db):
        original(db)
        db.execute('CREATE TABLE should_rollback(value)')
        db.execute("UPDATE works SET title='wrong'")
        raise RuntimeError('injected migration failure')
    monkeypatch.setitem(migrations.MIGRATIONS, 2, fail)
    with pytest.raises(RuntimeError, match='injected'):
        Library(directory)
    with sqlite3.connect(directory / 'library.sqlite') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0
        assert db.execute('SELECT title FROM works').fetchone()[0] == '保留资料'
        assert 'liked' not in {row[1] for row in db.execute('PRAGMA table_info(works)')}
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='should_rollback'").fetchone()
    monkeypatch.setitem(migrations.MIGRATIONS, 2, original)
    lib = Library(directory)
    assert lib.work(1)['liked'] == 1
    lib.close()


def test_backup_failure_prevents_all_migration(tmp_path, monkeypatch):
    directory = tmp_path / 'old'
    legacy(directory)
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr(migrations, 'backup_before_upgrade', fail)
    with pytest.raises(OSError, match='disk full'): Library(directory)
    with sqlite3.connect(directory / 'library.sqlite') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0
        assert 'liked' not in {row[1] for row in db.execute('PRAGMA table_info(works)')}


@pytest.mark.parametrize('initialize', [True, False])
def test_newer_schema_is_rejected_without_writes(tmp_path, initialize):
    directory = tmp_path / 'future'
    legacy(directory, migrations.SCHEMA_VERSION + 1)
    path = directory / 'library.sqlite'
    original = path.read_bytes()
    with pytest.raises(ValueError, match='较新客户端'): Library(directory, initialize=initialize)
    assert path.read_bytes() == original
    assert not (directory / 'backups').exists()


def test_restore_rejects_future_schema_and_migrates_unversioned_copy(library, tmp_path):
    directory = tmp_path / 'legacy'
    legacy(directory)
    path = directory / 'library.sqlite'
    original = path.read_bytes()
    restore_database(library, path)
    assert library.work(1)['liked'] == 1 and path.read_bytes() == original
    assert library.db.execute('PRAGMA user_version').fetchone()[0] == migrations.SCHEMA_VERSION
    with sqlite3.connect(path) as db: db.execute('PRAGMA user_version=100')
    with pytest.raises(ValueError, match='较新客户端'): restore_database(library, path)
    assert library.work(1)['title'] == '保留资料'


def test_current_version_structural_damage_is_not_silently_repaired(library):
    directory = library.directory
    library.db.execute('DROP TABLE bookmarks')
    library.db.commit()
    with pytest.raises(ValueError, match='结构与版本不一致'): Library(directory)
