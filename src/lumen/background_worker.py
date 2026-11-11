"""Short-lived automatic jobs; heavyweight image libraries leave with the worker."""
from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time

from .core import Library, ImportCancelled, check_cancelled, set_tool_directory

JOBS = ('watch', 'media', 'inspect', 'discovery')
MAX_RESULT_BYTES = 16 * 1024


def _summary(value):
    """Report useful counts without copying paths, provider messages or credentials."""
    result = {}
    for key in ('imported', 'updated', 'waiting', 'completed', 'pending', 'retry',
                'scanned', 'missing', 'renamed', 'refreshed', 'due', 'errors', 'offline'):
        item = value.get(key)
        if isinstance(item, (list, tuple)):
            result[key] = len(item)
        elif type(item) is int:
            result[key] = max(0, item)
    for key in ('cancelled', 'needs_ffmpeg', 'skipped'):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    if isinstance(value.get('automation'), dict):
        result['automation'] = _summary(value['automation'])
    return result


def _perform(job, library, cancelled):
    def progress(*args, **kwargs):
        check_cancelled(cancelled)
    progress.cancelled = cancelled
    if job == 'watch':
        from .media_tools import watch_folders
        from .ingestion import process_pending
        result = watch_folders(library, progress, cancelled=cancelled)
        result['automation'] = process_pending(library, progress, cancelled)
        return result
    if job == 'media':
        return library.enrich_pending(progress, cancelled=cancelled)
    if job == 'inspect':
        state = library.setting('inspection', {})
        if state.get('last') and time.time() - state['last'] < 2 * 3600:
            return {'skipped': True}
        return library.inspect_batch(progress=progress, cancelled=cancelled)
    if job == 'discovery':
        from .plugins import Plugins
        manager = Plugins(library)
        current = time.time()
        due = [plugin['id'] for plugin in manager.installed()
               if plugin['config'].get('enabled') and 'discover' in plugin['capabilities']
               and plugin['config'].get('auto_refresh', False)
               and current - max(plugin['config'].get('last_refresh', 0), plugin['config'].get('last_attempt', 0))
               > max(1, plugin['config'].get('interval_hours', 24)) * 3600]
        result = {'due': len(due), 'refreshed': 0, 'errors': 0}
        for identifier in due:
            check_cancelled(cancelled)
            try:
                manager.refresh(identifier)
                result['refreshed'] += 1
            except ImportCancelled:
                raise
            except Exception:
                result['errors'] += 1
        return result
    raise ValueError('Unknown background job')


def _write_result(result, result_file):
    payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
    if len(payload.encode('utf-8')) > MAX_RESULT_BYTES:
        raise ValueError('Background result is too large')
    if result_file:
        destination = Path(result_file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         prefix=destination.name + '.', suffix='.tmp',
                                         dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload + '\n')
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    if sys.stdout is not None:
        print(payload, flush=True)


def run(job, directory, cancel_file=None, result_file=None):
    """Return 0 for success, 2 for cooperative cancellation, 1 for failure."""
    stopped = threading.Event()
    marker = Path(cancel_file) if cancel_file else None
    def cancelled():
        return stopped.is_set() or marker is not None and marker.exists()
    previous_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for number in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[number] = signal.signal(number, lambda *_: stopped.set())
    previous_worker = os.environ.get('LUMEN_BACKGROUND_WORKER')
    previous_directory = os.environ.get('LUMEN_DATA_DIR')
    os.environ['LUMEN_BACKGROUND_WORKER'] = '1'
    os.environ['LUMEN_DATA_DIR'] = str(Path(directory).resolve())
    library = None
    handler = None
    logger = logging.getLogger('lumen.background_worker')
    result = {'job': job if job in JOBS else 'unknown', 'status': 'failed', 'summary': {}}
    code = 1
    try:
        if job not in JOBS:
            raise ValueError('Unknown background job')
        check_cancelled(cancelled)
        library = Library(directory)
        library.cancelled = cancelled
        set_tool_directory(library.setting('ffmpeg_directory', ''))
        handler = RotatingFileHandler(library.directory / 'background-worker.log',
                                      maxBytes=256 * 1024, backupCount=1, encoding='utf-8')
        logger.addHandler(handler)
        outcome = _perform(job, library, cancelled)
        result['summary'] = _summary(outcome)
        check_cancelled(cancelled)
        if outcome.get('cancelled'):
            raise ImportCancelled('Background work cancelled')
        partial = bool(result['summary'].get('errors'))
        result['status'] = 'partial' if partial else 'done'
        code = 1 if partial else 0
    except ImportCancelled:
        result['status'] = 'cancelled'
        code = 2
    except Exception as error:
        result['error_type'] = type(error).__name__[:80]
        # Detailed operation failures remain in their existing durable task rows.
        # Never echo an exception's source URL, file path or access key over IPC.
        logger.error('Automatic job %s failed (%s)', result['job'], result['error_type'])
    finally:
        if library is not None:
            library.close()
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()
        for number, previous in previous_handlers.items():
            signal.signal(number, previous)
        for key, previous in (('LUMEN_BACKGROUND_WORKER', previous_worker), ('LUMEN_DATA_DIR', previous_directory)):
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
    try:
        _write_result(result, result_file)
    except (OSError, ValueError):
        return 1
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run one automatic Lumen job')
    parser.add_argument('job', choices=JOBS)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--cancel-file')
    parser.add_argument('--result-file')
    args = parser.parse_args(argv)
    return run(args.job, args.data_dir, args.cancel_file, args.result_file)


if __name__ == '__main__':
    raise SystemExit(main())
