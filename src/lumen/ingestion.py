"""Persistent automatic identification shared by manual import and watched folders."""
import json
import re
import time
import uuid
import threading
from pathlib import Path
from .core import check_cancelled, ImportCancelled
from .plugins import Plugins
from .files import plan_move, execute_move


_processing = threading.Lock()


class NeedsConfirmation(ValueError):
    pass


def codes(text):
    text = str(text).upper()
    found = set()
    for match in re.finditer(r'(?<![A-Z0-9])(?:FC2[-_ ]*(?:PPV[-_ ]*)?(\d{5,9})|([A-Z]{2,10})[-_ ]*(\d{2,7}))(?![A-Z0-9])', text):
        if match[1]:
            found.add('FC2-PPV-' + match[1])
        elif match[2] not in {'CD', 'PART', 'DISC', 'HEVC', 'H264', 'H265'}:
            if re.search(r'\s', match[0]) and len(match[3]) == 4 and 1800 <= int(match[3]) <= 2200:
                continue
            found.add(match[2] + '-' + match[3])
    return found


def work_codes(work):
    # Inspect file basenames and immediate folders, never unrelated ancestor paths.
    if work['kind'] == 'series':
        return set()
    values = [work['title']]
    external=work.get('metadata',{}).get('external_ids',{})
    values.extend(str(external[key]) for key in ('product_code','catalog_number') if external.get(key))
    for file in work['files']:
        path = Path(file['path'])
        values.extend((path.stem, path.parent.name))
    return set().union(*(codes(value) for value in values))


def choose(work, candidates):
    identifiers = work_codes(work)
    if len(identifiers) > 1:
        raise NeedsConfirmation('文件含多个编号，请确认作品或分段归组')
    matches = []
    for candidate in candidates:
        kind = candidate.get('kind', 'movie')
        if kind != work['kind'] and not (work['kind'] == 'vr' and kind == 'movie'):
            continue
        if identifiers:
            external=candidate.get('external_ids', {})
            # Provider IDs can be opaque alphanumeric slugs; prefer an explicit product code.
            product=external.get('product_code') or external.get('catalog_number')
            values=[str(product)] if product else [candidate.get('title', ''), candidate.get('id', '')]
            matched = set().union(*(codes(value) for value in values)) == identifiers
        else:
            matched = (candidate['title'].casefold().strip() == work['title'].casefold().strip()
                       and (not work['year'] or candidate.get('year') == work['year']))
        if matched:
            matches.append(candidate)
    unique = {str(candidate['id']): candidate for candidate in matches}
    if len(unique) != 1:
        raise NeedsConfirmation('未找到唯一匹配，请在详情确认编号或候选；原文件未整理')
    return next(iter(unique.values()))


def enqueue(library, work, plugin, destination, force=False, fallback_plugins=None):
    if work['kind'] not in {'movie', 'series', 'vr'} or not (plugin or destination):
        return
    identifier = 'ingest-' + str(work['id'])
    previous = library.db.execute('SELECT status,payload FROM tasks WHERE id=?', (identifier,)).fetchone()
    file_ids = sorted(file['id'] for file in work['files'])
    if previous:
        if previous['status'] != 'done': return
        if not force and json.loads(previous['payload']).get('file_ids') == file_ids: return
    payload = {'work_id': work['id'], 'title': work['title'], 'plugin': plugin or '', 'destination': destination or '',
               'stage': 'identify', 'attempts': 0, 'next_attempt': 0, 'file_ids': file_ids,
               'move_id': identifier + '-move-' + uuid.uuid4().hex,
               'fallback_plugins': fallback_plugins if fallback_plugins is not None else library.setting('numbered_fallbacks:'+work['kind'],[])}
    library.task(identifier, 'ingest', 'queued', payload)


def process_pending(library, progress=None, cancelled=None, limit=10, clock=time.time):
    # Multiple manually queued imports may run concurrently; only one worker owns stages.
    while not _processing.acquire(timeout=.1):
        check_cancelled(cancelled)
    try:
        return _process_pending(library, progress, cancelled, limit, clock)
    finally:
        _processing.release()


def _process_pending(library, progress=None, cancelled=None, limit=10, clock=time.time):
    rows = library.db.execute("SELECT * FROM tasks WHERE kind='ingest' AND status IN ('queued','running','retry') AND COALESCE(json_extract(payload, '$.next_attempt'),0)<=? ORDER BY updated LIMIT ?", (clock(), limit)).fetchall()
    summary = {'completed': 0, 'pending': 0, 'retry': 0}
    for index, row in enumerate(rows):
        check_cancelled(cancelled)
        payload = json.loads(row['payload'])
        if payload.get('next_attempt', 0) > clock():
            continue
        def save(status, error=None):
            library.task(row['id'], 'ingest', status, payload, error=error)
        try:
            work = library.work(payload['work_id'])
            if progress: progress(index, len(rows), '自动入库 · ' + work['title'])
            save('running')
            if payload['stage'] == 'identify':
                if payload['plugin']:
                    from .numbered_sources import resolve, SourceLookupError
                    try:
                        found=resolve(library,work,payload['plugin'],payload.get('fallback_plugins',[]),cancelled)
                    except SourceLookupError as error:
                        payload['source_attempts']=error.attempts
                        if error.candidates:
                            payload['candidates']=error.candidates;payload['plugin']=error.plugin
                        if error.retryable:raise
                        raise NeedsConfirmation(str(error)) from error
                    payload['source_attempts']=found['attempts']
                    payload['matched_plugin']=found['plugin']
                    Plugins(library).merge(found['plugin'],found['candidate'],work['id'])
                payload.pop('candidates', None)
                payload['stage'] = 'organize'
                save('running')
            check_cancelled(cancelled)
            if payload['destination']:
                # Reuse the move journal after interruption; never create a second plan.
                move_id = payload['move_id']
                exists = library.db.execute('SELECT status FROM tasks WHERE id=?', (move_id,)).fetchone()
                if exists:
                    if exists['status'] != 'done': execute_move(library, task_id=move_id)
                else:
                    execute_move(library, plan_move(library, work['id'], payload['destination']), task_id=move_id)
            save('done'); summary['completed'] += 1
        except ImportCancelled:
            save('queued'); raise
        except (NeedsConfirmation, FileExistsError) as exc:
            save('pending', str(exc)); summary['pending'] += 1
        except Exception as exc:
            payload['attempts'] += 1
            payload['next_attempt'] = clock() + min(3600, 30 * 2 ** min(payload['attempts'], 7))
            save('retry' if payload['attempts'] < 5 else 'pending', str(exc))
            summary['retry'] += 1
    return summary


def confirm(library, work_id):
    identifier = 'ingest-' + str(work_id)
    row = library.db.execute("SELECT payload FROM tasks WHERE id=? AND status != 'done'", (identifier,)).fetchone()
    if row:
        payload = json.loads(row['payload']); payload.update(stage='organize', attempts=0, next_attempt=0)
        library.task(identifier, 'ingest', 'queued', payload)
