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


def task_identifier(work_id,media_library_id=None):
    return 'ingest-'+str(work_id)+('-library-'+str(media_library_id) if media_library_id is not None else '')


def enqueue(library, work, plugin, destination, force=False, fallback_plugins=None, media_library_id=None, naming_rule=None):
    if media_library_id is None:
        owners={r[0] for r in library.db.execute('SELECT DISTINCT m.library_id FROM media_library_files m JOIN files f ON f.id=m.file_id WHERE f.work_id=?',(work['id'],))}
        if owners:
            from .media_libraries import get
            for owner in owners:
                cfg=get(library,owner)['config']
                enqueue(library,library.work(work['id'],owner),cfg['plugin'],cfg['destination'],force,cfg['fallback_plugins'],owner,cfg['naming'])
            owned={r[0] for r in library.db.execute('SELECT file_id FROM media_library_files')}
            work={**work,'files':[f for f in work['files'] if f['id'] not in owned]}
            if not work['files']:return
    if work['kind'] not in {'movie', 'series', 'vr'} or not (plugin or destination):
        return
    identifier = task_identifier(work['id'],media_library_id)
    previous = library.db.execute('SELECT status,payload FROM tasks WHERE id=?', (identifier,)).fetchone()
    file_ids = sorted(file['id'] for file in work['files'])
    if previous:
        if previous['status']=='running' or previous['status']!='done' and not force:return
        if not force and json.loads(previous['payload']).get('file_ids') == file_ids: return
    payload = {'work_id': work['id'], 'title': work['title'], 'plugin': plugin or '', 'destination': destination or '',
               'stage': 'identify', 'attempts': 0, 'next_attempt': 0, 'file_ids': file_ids,
               'move_id': identifier + '-move-' + uuid.uuid4().hex,
               'fallback_plugins': fallback_plugins if fallback_plugins is not None else library.setting('numbered_fallbacks:'+work['kind'],[])}
    if media_library_id is not None:payload.update(media_library_id=media_library_id,naming_rule=naming_rule or {})
    library.task(identifier, 'ingest', 'queued', payload)


def process_pending(library, progress=None, cancelled=None, limit=10, clock=time.time, work_ids=None, media_library_id=None):
    # Multiple manually queued imports may run concurrently; only one worker owns stages.
    while not _processing.acquire(timeout=.1):
        check_cancelled(cancelled)
    try:
        return _process_pending(library, progress, cancelled, limit, clock, work_ids, media_library_id)
    finally:
        _processing.release()


def _process_pending(library, progress=None, cancelled=None, limit=10, clock=time.time, work_ids=None, media_library_id=None):
    scoped='';parameters=[clock()]
    if work_ids is not None:
        work_ids=list(dict.fromkeys(work_ids))
        if not work_ids:return {'completed':0,'pending':0,'retry':0}
        scoped=" AND json_extract(payload,'$.work_id') IN ("+','.join('?' for _ in work_ids)+')'
        parameters.extend(work_ids)
    if media_library_id is not None:
        scoped+=" AND json_extract(payload,'$.media_library_id')=?";parameters.append(media_library_id)
    parameters.append(limit)
    rows = library.db.execute("SELECT * FROM tasks WHERE kind='ingest' AND status IN ('queued','running','retry') AND COALESCE(json_extract(payload, '$.next_attempt'),0)<=?"+scoped+" ORDER BY updated LIMIT ?", parameters).fetchall()
    summary = {'completed': 0, 'pending': 0, 'retry': 0}
    for index, row in enumerate(rows):
        check_cancelled(cancelled)
        payload = json.loads(row['payload'])
        if payload.get('next_attempt', 0) > clock():
            continue
        def save(status, error=None):
            library.task(row['id'], 'ingest', status, payload, error=error)
        try:
            # Claim before resolving ownership: deletion can now see an active task.
            current=library.db.execute('SELECT status FROM tasks WHERE id=?',(row['id'],)).fetchone()
            if not current or current[0] not in {'queued','running','retry'}:continue
            save('running')
            scoped_id=payload.get('media_library_id')
            work=library.work(payload['work_id'],scoped_id) if scoped_id is not None else library.work(payload['work_id'])
            if scoped_id is None:
                owned={r[0] for r in library.db.execute('SELECT file_id FROM media_library_files')}
                if any(f['id'] in owned for f in work['files'] if f['id'] in payload['file_ids']):raise NeedsConfirmation('文件已归入自定义媒体库，请从对应媒体库重新扫描')
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
                    manager=Plugins(library);manager.cancelled=cancelled
                    merged_id=manager.merge(found['plugin'],found['candidate'],work['id'])
                    if merged_id is not None and merged_id!=work['id']:
                        payload['work_id']=merged_id
                        work=library.work(merged_id,scoped_id) if scoped_id is not None else library.work(merged_id)
                payload.pop('candidates', None)
                payload['stage'] = 'organize'
                save('running')
            check_cancelled(cancelled)
            if payload['destination']:
                # Reuse the move journal after interruption; never create a second plan.
                move_id = payload['move_id']
                exists = library.db.execute('SELECT status FROM tasks WHERE id=?', (move_id,)).fetchone()
                if exists:
                    if exists['status'] != 'done': execute_move(library, task_id=move_id,cancelled=cancelled)
                else:
                    execute_move(library, plan_move(library, work['id'], payload['destination'],cancelled=cancelled, **({'media_library_id':scoped_id,'rule':payload.get('naming_rule',{})} if scoped_id is not None else {'file_ids':payload['file_ids']})), task_id=move_id,cancelled=cancelled)
            save('done'); summary['completed'] += 1
        except ImportCancelled:
            save('queued'); raise
        except (NeedsConfirmation, FileExistsError) as exc:
            save('pending', str(exc)); summary['pending'] += 1
        except Exception as exc:
            if payload.get('media_library_id') is not None and not library.db.execute('SELECT 1 FROM media_libraries WHERE id=?',(payload['media_library_id'],)).fetchone():
                save('cancelled',str(exc));continue
            payload['attempts'] += 1
            payload['next_attempt'] = clock() + min(3600, 30 * 2 ** min(payload['attempts'], 7))
            save('retry' if payload['attempts'] < 5 else 'pending', str(exc))
            summary['retry'] += 1
    return summary


def confirm(library, work_id, media_library_id=None):
    scope=" AND json_extract(payload,'$.media_library_id') IS NULL" if media_library_id is None else " AND json_extract(payload,'$.media_library_id')=?"
    args=(work_id,) if media_library_id is None else (work_id,media_library_id)
    rows=library.db.execute("SELECT id,payload FROM tasks WHERE kind='ingest' AND status IN ('pending','retry','queued') AND json_extract(payload,'$.work_id')=?"+scope,args).fetchall()
    for row in rows:
        payload=json.loads(row['payload'])
        if payload.get('media_library_id') is not None:
            from .media_libraries import get
            try:get(library,payload['media_library_id'])
            except ValueError:continue
        payload.update(stage='organize',attempts=0,next_attempt=0)
        library.task(row['id'],'ingest','queued',payload)
