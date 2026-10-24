from pathlib import Path
import sqlite3
import uuid
import tempfile


def restore_database(library, path):
    path = Path(path).resolve(strict=True)
    if path == (library.directory / 'library.sqlite').resolve():
        raise ValueError('请选择独立备份文件')
    source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    staging=None
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('备份完整性检查失败')
        expected = {r[0]: r[1] for r in library.db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
        actual = {r[0]: r[1] for r in source.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
        missing=set(expected)-set(actual)
        legacy_works=expected['works'].replace(', liked INTEGER NOT NULL DEFAULT 0 CHECK(liked IN (0,1))','')
        migrate_liked=actual.get('works')==legacy_works and legacy_works!=expected['works']
        if set(actual)-set(expected) or missing-{'bookmarks','playback_preferences'} or any(actual[name]!=expected[name] and not (name=='works' and migrate_liked) for name in actual):
            raise ValueError('备份格式或版本不兼容')
        if missing or migrate_liked:
            # Migrate a copy; a user's original backup always remains unchanged.
            staging=tempfile.TemporaryDirectory(prefix='lumen-restore-')
            staged=Path(staging.name)/'library.sqlite'
            copy=sqlite3.connect(staged);source.backup(copy);copy.close();source.close()
            from .core import Library
            migrated=Library(staging.name);migrated.close()
            source=sqlite3.connect(staged.as_uri()+'?mode=ro',uri=True)
        if source.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('备份关系完整性检查失败')
        library.backup(library.directory / ('before-restore-' + uuid.uuid4().hex + '.sqlite'))
        source.backup(library.db)
        library.db.execute('PRAGMA foreign_keys=ON')
    finally:
        source.close()
        if staging:staging.cleanup()
