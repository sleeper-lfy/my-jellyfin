"""Ordered, atomic schema upgrades. Never open a newer library for writing."""
from contextlib import closing
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import uuid

from .schema import BASELINE

SCHEMA_VERSION = 2


def baseline(db):
    # executescript implicitly commits; execute complete statements individually
    # so DDL and data migrations share the same rollback boundary.
    statement = ''
    for line in BASELINE.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ''
    if statement.strip():
        raise ValueError('数据库迁移脚本不完整')


def unified_preferences(db):
    if 'liked' not in {row[1] for row in db.execute('PRAGMA table_info(works)')}:
        db.execute('ALTER TABLE works ADD COLUMN liked INTEGER NOT NULL DEFAULT 0 CHECK(liked IN (0,1))')
    row = db.execute("SELECT value FROM settings WHERE key='personal_unified_v1'").fetchone()
    if not row or row[0] != 'true':
        db.execute('UPDATE works SET favorite=CASE WHEN disliked THEN 0 ELSE MAX(favorite,liked) END,liked=CASE WHEN disliked THEN 0 ELSE MAX(favorite,liked) END')
        db.execute("INSERT OR REPLACE INTO settings VALUES ('personal_unified_v1','true')")


MIGRATIONS = {1: baseline, 2: unified_preferences}


def validate_schema(db):
    # Versioned databases must never be silently "repaired" as legacy databases.
    required = {'works', 'files', 'import_cache', 'sources', 'name_keys', 'external_ids',
                'sessions', 'activity', 'tasks', 'settings', 'lists', 'playback_preferences', 'bookmarks'}
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= tables or 'liked' not in {row[1] for row in db.execute('PRAGMA table_info(works)')}:
        raise ValueError('数据库结构与版本不一致，请从备份恢复，未自动修改数据库')


def backup_before_upgrade(directory, version):
    folder = directory / 'backups'
    folder.mkdir(exist_ok=True)
    name = f'schema-{version}-to-{SCHEMA_VERSION}-{uuid.uuid4().hex}.sqlite'
    target = folder / name
    temporary = target.with_suffix('.tmp')
    try:
        # The migration connection holds BEGIN IMMEDIATE, blocking other writers.
        # A separate reader copies the last committed state, including WAL pages.
        with closing(sqlite3.connect((directory / 'library.sqlite').resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination)
                if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('升级前备份校验失败')
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def initialize_database(db, directory, *, initialize=True):
    directory = Path(directory)
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError(f'数据库版本 {version} 高于当前程序支持的 {SCHEMA_VERSION}，请使用较新客户端；未修改数据库')
    db.execute('PRAGMA foreign_keys=ON')
    if not initialize:
        if version != SCHEMA_VERSION:
            raise ValueError('数据库尚未升级，请先由主程序打开')
        return
    if version == SCHEMA_VERSION:
        validate_schema(db)
        return
    # Journal setup only after rejecting newer schemas.
    if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':
        db.execute('PRAGMA journal_mode=WAL')
    backup = None
    db.execute('BEGIN IMMEDIATE')
    try:
        # Another opener may have completed the upgrade while we waited.
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError('数据库已由较新客户端升级，请更新程序')
        if version < SCHEMA_VERSION:
            existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()
            if existing:
                backup = backup_before_upgrade(directory, version)
            for next_version in range(version + 1, SCHEMA_VERSION + 1):
                MIGRATIONS[next_version](db)
                db.execute(f'PRAGMA user_version={next_version}')
            validate_schema(db)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('升级后数据库关系校验失败')
            db.execute("INSERT OR REPLACE INTO settings VALUES ('schema_migration_completed', ?)",
                       ('"' + datetime.now(timezone.utc).isoformat() + '"',))
        db.commit()
    except BaseException:
        db.rollback()
        logging.exception('Database migration failed; changes rolled back; backup=%s', backup)
        raise
    logging.info('Database schema ready: %s -> %s; backup=%s', version, SCHEMA_VERSION, backup)
