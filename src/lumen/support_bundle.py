"""Allowlisted diagnostic export: no database, free-form settings or raw logs."""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import tempfile
import zipfile

from . import __version__
from .core import Library, tool
from .migrations import SCHEMA_VERSION

LOG_NAMES = ('diagnostics.log', 'diagnostics.log.1', 'ui-hangs.log', 'ui-native-hangs.log')
SAFE_SETTINGS = {'background_concurrency': (1, 3), 'poster_width': (120, 300), 'thumbnail_width': (200, 480)}
STACK_MODULES = {'app.py', 'core.py', 'ui.py', 'player.py', 'mpv_backend.py', 'migrations.py',
                 'plugins.py', 'downloads.py', 'updates.py', 'updates_ui.py', 'images.py',
                 'background.py', 'settings.py', 'support_bundle.py', 'server.py',
                 'task_journal.py', 'playback_journal.py', 'diagnostics.py'}


def collect_report(directory, backend='unknown'):
    library = Library(directory, initialize=False)
    try:
        settings = {}
        for key, (low, high) in SAFE_SETTINGS.items():
            value = library.setting(key)
            if type(value) is int and low <= value <= high:
                settings[key] = value
        report = {
            'format_version': 1, 'created': datetime.now(timezone.utc).isoformat(),
            'application': __version__, 'system': platform.system(), 'release': platform.release(),
            'architecture': platform.machine(), 'python': platform.python_version(),
            'sqlite': sqlite3.sqlite_version,
            'schema': library.db.execute('PRAGMA user_version').fetchone()[0],
            'supported_schema': SCHEMA_VERSION,
            'backend': backend if backend in ('libmpv', 'Qt Multimedia') else 'unknown',
            'tools': {name: bool(tool(name)) for name in ('ffmpeg', 'ffprobe')},
            'settings': settings,
            'counts': {table: library.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                       for table in ('works', 'files', 'tasks')},
            'privacy': '不含数据库、影片标题、文件路径、密钥、Cookie、原始日志消息或插件配置。日志仅保留级别、时间和程序堆栈位置。',
        }
        completed = library.setting('schema_migration_completed')
        if isinstance(completed, str):
            try: report['last_migration'] = datetime.fromisoformat(completed).isoformat()
            except ValueError: pass
        logs = {}
        for name in LOG_NAMES:
            path = Path(directory) / name
            if not path.is_file() or path.is_symlink():
                continue
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 256 * 1024))
                lines = stream.read(256 * 1024).decode('utf-8', errors='replace').splitlines()
            events, frames = [], []
            for line in lines:
                match = re.match(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) (DEBUG|INFO|WARNING|ERROR|CRITICAL)\b', line)
                if match:
                    events.append({'time': match[1], 'level': match[2]})
                frame = re.match(r'^\s*File "[^"]*[/\\]lumen[/\\]([a-z_]+\.py)", line (\d+), in ([A-Za-z_][A-Za-z_0-9]*)\s*$', line)
                if frame and frame[1] in STACK_MODULES:
                    frames.append({'module': frame[1], 'line': int(frame[2])})
            logs[name] = {'levels': dict(Counter(event['level'] for event in events)),
                          'events': events[-200:], 'frames': frames[-100:], 'tail_limit_bytes': 256 * 1024}
        report['logs'] = logs
        return report
    finally:
        library.close()


def export_report(report, destination):
    destination = Path(destination)
    if destination.suffix.lower() != '.zip':
        raise ValueError('诊断包请保存为 .zip 文件')
    descriptor, temporary = tempfile.mkstemp(prefix='.lumen-diagnostics-', suffix='.tmp', dir=destination.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('report.json', json.dumps(report, ensure_ascii=False, indent=2))
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def show_export(window):
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QFileDialog, QMessageBox
    from .background import run_background
    from .ui import button
    directory = window.library.directory
    backend = 'libmpv' if window.player.mpv_backend else 'Qt Multimedia'

    def preview(report):
        dialog = QDialog(window)
        dialog.setWindowTitle('导出诊断包 · 内容预览')
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(json.dumps(report, ensure_ascii=False, indent=2))
        text.setReadOnly(True)
        layout.addWidget(text)

        def save():
            path, _ = QFileDialog.getSaveFileName(dialog, '保存诊断包', 'Lumen-diagnostics.zip', 'ZIP (*.zip)')
            if not path:
                return
            try:
                export_report(report, path)
                QMessageBox.information(dialog, '诊断包已保存', path)
                dialog.accept()
            except Exception as error:
                QMessageBox.warning(dialog, '导出失败', str(error))

        layout.addWidget(button('保存诊断包…', save, True))
        layout.addWidget(button('关闭', dialog.reject))
        dialog.exec()

    return run_background(window, lambda job: collect_report(directory, backend), preview,
                          lambda error: QMessageBox.warning(window, '收集诊断失败', error))
