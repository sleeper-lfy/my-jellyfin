from pathlib import Path
import sqlite3
import uuid


def restore_database(library, path):
    path = Path(path).resolve(strict=True)
    if path == (library.directory / 'library.sqlite').resolve():
        raise ValueError('请选择独立备份文件')
    source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('备份完整性检查失败')
        expected = {r[0]: r[1] for r in library.db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
        actual = {r[0]: r[1] for r in source.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
        if expected != actual:
            raise ValueError('备份格式或版本不兼容')
        if source.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('备份关系完整性检查失败')
        library.backup(library.directory / ('before-restore-' + uuid.uuid4().hex + '.sqlite'))
        source.backup(library.db)
        library.db.execute('PRAGMA foreign_keys=ON')
    finally:
        source.close()
