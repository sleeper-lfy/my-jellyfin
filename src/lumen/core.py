from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone
from collections import Counter

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v', '.webm', '.mpg', '.mpeg', '.ts', '.m2ts', '.flv', '.rm', '.rmvb', '.asf', '.vob', '.ogv', '.mts', '.3gp', '.3g2', '.divx', '.f4v', '.m2v', '.m2t'}
SIDECARS = {'.srt', '.ass', '.ssa', '.vtt', '.sub', '.idx', '.nfo', '.jpg', '.png'}


def actor_defaults(metadata, kind):
    """Apply movie defaults at read time, preserving the imported source value on disk."""
    if kind in {'movie', 'vr'} and 'actors' in metadata:
        metadata = {**metadata, 'actors': [
            {**actor, 'gender': 'female'} if actor.get('gender') in (None, '', 'unknown') else actor
            for actor in metadata['actors']]}
    return metadata


def now():
    return datetime.now(timezone.utc).isoformat()


def data_directory():
    return Path(os.environ.get('LUMEN_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'Lumen')


class ImportCancelled(Exception):
    """Cooperative stop at a safe transaction boundary."""


def check_cancelled(cancelled):
    if cancelled and cancelled():
        raise ImportCancelled('任务已停止，已完成的记录已保留')


def media_process(command, timeout, cancelled=None):
    check_cancelled(cancelled)
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=0x08000000 if os.name == 'nt' else 0) as process:
        start = time.monotonic()
        try:
            while True:
                check_cancelled(cancelled)
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.kill()
            process.communicate()
            raise
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def fingerprint(path, progress=None, cancelled=None):
    digest = hashlib.sha256()
    size = Path(path).stat().st_size
    processed = 0
    reported = time.monotonic()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            check_cancelled(cancelled)
            digest.update(block)
            processed += len(block)
            if progress and (time.monotonic() - reported >= .25 or processed == size):
                progress(processed, size)
                reported = time.monotonic()
    return digest.hexdigest()


def quick_fingerprint(path):
    """Candidate index only: never use sampled content as proof of equality."""
    size = Path(path).stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with Path(path).open('rb') as stream:
        for offset in sorted({0, max(0, size // 2 - 32768), max(0, size - 65536)}):
            stream.seek(offset)
            digest.update(stream.read(65536))
    return digest.hexdigest()


def parse_name(path, kind):
    stem = Path(path).stem
    episode = re.search(r'(?i)(?:s(\d{1,2})[ ._-]*e(\d{1,3})|(\d{1,2})x(\d{1,3}))', stem)
    year_match = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', stem)
    end = min([m.start() for m in (episode, year_match) if m] or [len(stem)])
    title = re.sub(r'[._]+', ' ', stem[:end]).strip(' -[]()') or stem
    season, number = (int(episode.group(1) or episode.group(3)), int(episode.group(2) or episode.group(4))) if episode else (1, 1)
    if kind == 'series':
        from .series import episode_numbers, season_folder
        season, number = episode_numbers(Path(path))
        if number is None and season_folder(Path(path).parent) is None:season=None
        if not episode:
            title = Path(path).parent.parent.name if season_folder(Path(path).parent) is not None else Path(path).parent.name
            title = title or stem
    if kind == 'other':
        title = stem
    if kind != 'other':
        title = re.split(r'(?i)\b(?:480p|720p|1080p|2160p|4k|bluray|bdrip|web[- ]?dl|webrip|hdtv|x264|x265|h264|h265)\b', title)[0].strip(' -[]()') or title
    return {'title': title, 'year': int(year_match.group()) if year_match else None,
            'season': season if kind == 'series' else None, 'episode': number if kind == 'series' else None}


def identity(title, year, kind):
    return f'{kind}:{re.sub(r"[^\w]", "", title.casefold())}:{year or ""}'


def tool(name):
    bundled = Path(__file__).resolve().parent / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))
    return str(bundled) if bundled.is_file() else shutil.which(name)


def probe(path, cancelled=None, *, local_only=False):
    executable = tool('ffprobe')
    if not executable:
        raise RuntimeError('未找到 ffprobe，请在设置说明中配置 FFmpeg PATH')
    result = media_process([executable, '-v', 'error', *(['-protocol_whitelist','file,pipe,crypto,data'] if local_only else []), '-show_format', '-show_streams', '-of', 'json', str(path)], 45, cancelled)
    info = json.loads(result.stdout)
    if not any(s.get('codec_type') == 'video' for s in info.get('streams', [])):
        raise ValueError('文件不含视频流')
    return float(info.get('format', {}).get('duration', 0))


def thumbnail(path, target, duration, at=None, cancelled=None):
    executable = tool('ffmpeg')
    if not executable:
        raise RuntimeError('未找到 ffmpeg')
    second = at if at is not None else min(max(duration * .15, 0), 300)
    media_process([executable, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(second), '-i', str(path),
                    '-frames:v', '1', '-vf', 'scale=480:-2', str(target)], 60, cancelled)
    if not Path(target).is_file():
        raise RuntimeError('未能生成缩略图')


from .catalog import CatalogActions, sort_items, watch_state


class Library(CatalogActions):
    def __init__(self, directory=None, *, initialize=True, timeout=30):
        self.directory = Path(directory or data_directory())
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / 'cache').mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.directory / 'library.sqlite', timeout=timeout)
        self.db.row_factory = sqlite3.Row
        from .migrations import initialize_database
        try:
            initialize_database(self.db, self.directory, initialize=initialize)
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def setting(self, key, default=None):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def work(self, work_id):
        row = self.db.execute('SELECT * FROM works WHERE id=?', (work_id,)).fetchone()
        if not row:
            raise ValueError('媒体不存在')
        item = dict(row)
        item['metadata'] = actor_defaults(json.loads(item['metadata']), item['kind'])
        item['liked'] = item['favorite']
        item['locked'] = json.loads(item['locked'])
        item['files'] = [dict(r) for r in self.db.execute('SELECT * FROM files WHERE work_id=? ORDER BY season,episode,path', (work_id,))]
        if item['kind'] in {'fans','vr'}:
            from .series import natural_key
            item['files'].sort(key=lambda file:natural_key(file['path']))
        for file in item['files']:
            details = item['metadata'].get('episode_details', {}).get(str(file['id']), {})
            file.update({key: details[key] for key in ['title','overview'] if key in details})
            file['stills']=item['metadata'].get('episode_stills',{}).get(str(file['id']),[])
        item['sources'] = [dict(r) for r in self.db.execute('SELECT * FROM sources WHERE work_id=?', (work_id,))]
        return item

    def update_personal(self, work_id, **fields):
        allowed = {'rating', 'favorite', 'watchlist', 'disliked', 'liked'}
        if not fields or not fields.keys() <= allowed:
            raise ValueError('无效个人字段')
        if 'rating' in fields and fields['rating'] is not None and (type(fields['rating']) is not int or not 1 <= fields['rating'] <= 10):
            raise ValueError('个人评分须为 1–10 整数或空')
        if 'liked' in fields:
            if type(fields['liked']) is not bool:raise ValueError('喜欢标记须为布尔值')
            if 'favorite' in fields and bool(fields['favorite'])!=fields['liked']:raise ValueError('喜欢与收藏是同一状态')
            fields['favorite']=fields['liked']
        if fields.get('favorite') and fields.get('disliked'):raise ValueError('喜欢 / 收藏与不喜欢不能同时选择')
        if 'favorite' in fields:fields['liked']=bool(fields['favorite'])
        if fields.get('favorite'):fields['disliked']=False
        elif fields.get('disliked'):fields.update(favorite=False,liked=False)
        with self.db:
            self.db.execute('UPDATE works SET ' + ','.join(f'{key}=?' for key in fields) + ' WHERE id=?', (*fields.values(), work_id))

    def merge_works(self, source_id, target_id, commit=True, *, allow_movie_vr=False):
        if source_id == target_id:
            return target_id
        source, target = self.work(source_id), self.work(target_id)
        cross_movie = source['kind'] != target['kind'] and {source['kind'],target['kind']} == {'movie','vr'}
        if source['kind'] == 'other' or source['kind'] != target['kind'] and not (allow_movie_vr and cross_movie):
            raise ValueError('仅可合并相同类型的影视或 Fans 条目')
        merged = {**source['metadata'], **target['metadata']}
        if source['kind']=='fans':
            from .fans import roots_for
            merged['fans_roots']=list(dict.fromkeys([*roots_for(target),*roots_for(source)]))
            merged['creator']=target['metadata'].get('creator') or target['title']
        for field in ('episode_details','episode_stills','nfo_thumbnails'):
            if field in source['metadata'] or field in target['metadata']:
                merged[field] = {**source['metadata'].get(field,{}), **target['metadata'].get(field,{})}
        merged['aliases'] = list(dict.fromkeys(source['metadata'].get('aliases',[]) + target['metadata'].get('aliases',[]) + ([source['title']] if source['title'] != target['title'] else [])))
        merged['external_ids'] = {**source['metadata'].get('external_ids',{}), **target['metadata'].get('external_ids',{})}
        with self.db if commit else nullcontext():
            self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(source['identity'],source_id))
            self.db.execute('UPDATE files SET work_id=? WHERE work_id=?', (target_id, source_id))
            self.db.execute('UPDATE sources SET work_id=? WHERE work_id=?', (target_id, source_id))
            self.db.execute('UPDATE works SET metadata=?,rating=?,favorite=?,watchlist=?,disliked=?,liked=?,discovered=?,thumbnail=? WHERE id=?',
                (json.dumps(merged, ensure_ascii=False), target['rating'] if target['rating'] is not None else source['rating'],
                 (target if target['favorite'] or target['disliked'] else source)['favorite'],max(target['watchlist'],source['watchlist']),
                 (target if target['favorite'] or target['disliked'] else source)['disliked'],
                 (target if target['favorite'] or target['disliked'] else source)['favorite'],
                 min([d for d in [target['discovered'],source['discovered']] if d] or [None]),target['thumbnail'] or source['thumbnail'],target_id))
            if cross_movie:
                # A discovered movie may be attached to a local VR movie. Keep all
                # identity indexes in the destination category, including refreshes.
                external = self.db.execute('SELECT namespace,value FROM external_ids WHERE work_id=?',(source_id,)).fetchall()
                for namespace,value in external:
                    owner=self.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?',(target['kind'],namespace,value)).fetchone()
                    if owner and owner[0] not in {source_id,target_id}:
                        raise ValueError('外部标识已关联另一部作品，请人工核对')
                self.db.execute('DELETE FROM name_keys WHERE work_id=?',(source_id,))
                for title in [source['title'],*source['metadata'].get('aliases',[])]:
                    self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(identity(title,source['year'],target['kind']),target_id))
                self.db.execute('DELETE FROM external_ids WHERE work_id=?',(source_id,))
                self.db.executemany('INSERT OR IGNORE INTO external_ids VALUES (?,?,?,?)',[(target['kind'],namespace,value,target_id) for namespace,value in external])
            else:
                self.db.execute('UPDATE name_keys SET work_id=? WHERE work_id=?', (target_id,source_id))
                self.db.execute('UPDATE external_ids SET work_id=? WHERE work_id=?', (target_id,source_id))
            self.db.execute('DELETE FROM works WHERE id=?', (source_id,))
            queue = self.setting('queue')
            if queue:
                current = queue['ids'][queue['index']] if queue['index'] < len(queue['ids']) else None
                queue['ids'] = list(dict.fromkeys(target_id if i == source_id else i for i in queue['ids']))
                current = target_id if current == source_id else current
                queue['index'] = queue['ids'].index(current) if current in queue['ids'] else len(queue['ids'])
                self.db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(queue), 'queue'))
        return target_id

    def edit_metadata(self, work_id, metadata, locked):
        item = self.work(work_id)
        item['metadata'].update(metadata)
        with self.db:
            self.db.execute('UPDATE works SET title=?,year=?,metadata=?,locked=? WHERE id=?',
                            (metadata.get('title', item['title']), metadata.get('year', item['year']), json.dumps(item['metadata'], ensure_ascii=False), json.dumps(locked), work_id))

    def set_movie_kind(self, work_id, kind):
        """Reclassify without moving media, changing IDs or losing watch records."""
        item = self.work(work_id)
        if kind not in {'movie', 'vr'} or item['kind'] not in {'movie', 'vr'}:
            raise ValueError('仅支持普通电影与 VR电影之间切换')
        if item['kind'] == kind:
            return
        titles = [item['title'], *item['metadata'].get('aliases', [])]
        keys = {identity(title, item['year'], kind) for title in titles}
        with self.db:
            for key in keys:
                existing = self.db.execute('SELECT work_id FROM name_keys WHERE key=?', (key,)).fetchone()
                if existing and existing[0] != work_id:
                    raise ValueError('目标分类已有同名作品，请先核对重复项')
            for external in self.db.execute('SELECT namespace,value FROM external_ids WHERE work_id=?',(work_id,)).fetchall():
                existing = self.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?', (kind,*external)).fetchone()
                if existing and existing[0] != work_id:
                    raise ValueError('目标分类已有相同外部标识，请先核对重复项')
            self.db.execute('UPDATE works SET kind=?,identity=? WHERE id=?',(kind,identity(item['title'],item['year'],kind),work_id))
            self.db.execute('DELETE FROM name_keys WHERE work_id=?',(work_id,))
            self.db.executemany('INSERT INTO name_keys VALUES (?,?)',[(key,work_id) for key in keys])
            self.db.execute('UPDATE external_ids SET kind=? WHERE work_id=?',(kind,work_id))

    def merge_fans_folders(self, work_ids, target_id, creator=None):
        from .fans import merge_folders
        return merge_folders(self,work_ids,target_id,creator)

    def import_folder(self, root, kind, progress=None, fast=False, cancelled=None, candidates=None):
        if kind=='fans':
            from .fans import import_folder
            return import_folder(self,root,progress,fast,cancelled,candidates)
        if kind not in {'movie', 'series', 'other', 'vr'}:
            raise ValueError('无效媒体类型')
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError('请选择文件夹')
        task_id = uuid.uuid4().hex
        payload = {'root': str(root), 'kind': kind, 'fast': fast}
        self.task(task_id, 'import', 'running', payload)
        results = {'imported': 0, 'duplicates': 0, 'errors': [], 'warnings': []}
        def report(done, total, stage, path='', force=True):
            payload['progress'] = {'completed': done, 'total': total, 'stage': stage, 'path': str(path)}
            if force or time.monotonic() - report.saved >= 1:
                self.task(task_id, 'import', 'running', payload, results)
                report.saved = time.monotonic()
            if progress:
                progress(done, total, stage + (' · ' + str(path) if path else ''))
        report.saved = 0
        directory_cache, signatures = {}, {}
        try:
            report(0, 0, '扫描文件夹', root)
            paths = []
            last_scan = time.monotonic()
            for candidate in (root.rglob('*') if candidates is None else map(Path,candidates)):
                check_cancelled(cancelled)
                if candidate.is_file() and not candidate.is_symlink() and candidate.suffix.lower() in VIDEO_EXTENSIONS and root in candidate.resolve().parents:
                    paths.append(candidate)
                if time.monotonic() - last_scan >= .25:
                    report(0, 0, f'扫描文件夹，已找到 {len(paths)} 个视频', candidate, False)
                    last_scan = time.monotonic()
            if kind in {'series','vr'}:
                from .series import SeriesPlan, natural_key
                paths.sort(key=natural_key)
                if kind == 'series':series_plan = SeriesPlan(self, paths, root, directory_cache, report, cancelled,partial=candidates is not None,fast=fast,signatures=signatures)
                else:
                    from .vr_folders import VRFolderPlan
                    vr_plan = VRFolderPlan(self, paths, cancelled)
            else:
                paths.sort()
            if fast:
                self.index_legacy_files(lambda text: report(0, len(paths), text, force=False), cancelled)
            for index, path in enumerate(paths):
                file_finished = True
                try:
                    check_cancelled(cancelled)
                    report(index, len(paths), '读取 NFO', path)
                    from . import nfo
                    stat = path.stat()
                    signature = nfo.sidecar_signature(path, root, kind, directory_cache, signatures) if fast else ''
                    existing_file = self.db.execute('SELECT id,work_id FROM files WHERE path=?',(str(path),)).fetchone()
                    if kind == 'vr':
                        group = vr_plan.group(path)
                        existing_file = vr_plan.reconcile(self,path,existing_file,results['warnings'])
                    if kind == 'series':
                        group = series_plan.group(path)
                        if existing_file and series_plan.existing[path]['kind'] == 'series':
                            with self.db:
                                if group['known'] != existing_file['work_id']:
                                    source = self.work(existing_file['work_id'])
                                    if all(Path(file['path']).is_relative_to(group['folder']) for file in source['files']):
                                        self.merge_works(source['id'], group['known'], commit=False)
                                        for other in series_plan.groups.values():
                                            if other['known']==source['id']:other['known']=group['known']
                                        existing_file = {'id': existing_file['id'], 'work_id': group['known']}
                                self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)', (group['key'], existing_file['work_id']))
                                self.db.execute('UPDATE files SET season=?,episode=? WHERE id=?', (*series_plan.numbers[path], existing_file['id']))
                    cache = self.db.execute('SELECT * FROM import_cache WHERE file_id=?', (existing_file['id'],)).fetchone() if existing_file else None
                    unchanged = cache and cache['size'] == stat.st_size and cache['modified'] == stat.st_mtime_ns
                    if fast and unchanged and cache['sidecars'] == signature:
                        results['duplicates'] += 1
                        continue
                    local = nfo.load(path, root, kind, results['warnings'], directory_cache)
                    if existing_file:
                        if fast and not unchanged:
                            quick = quick_fingerprint(path)
                            with self.db:
                                self.db.execute("UPDATE files SET digest=?,duration=0 WHERE id=?", ('fast-' + uuid.uuid4().hex, existing_file['id']))
                                self.db.execute('INSERT OR REPLACE INTO import_cache VALUES (?,?,?,?,?,?,?)', (existing_file['id'],stat.st_size,stat.st_mtime_ns,quick,None,signature,1))
                        if local['work'] or local['entry'] or local['poster'] or local.get('backdrop'):
                            with self.db:
                                nfo.apply(self,existing_file['work_id'],existing_file['id'],local,False,False,root,results['warnings'])
                            results['nfo_updated'] = results.get('nfo_updated',0) + 1
                        if fast:
                            with self.db:
                                self.db.execute('UPDATE import_cache SET sidecars=? WHERE file_id=?', (signature,existing_file['id']))
                        results['duplicates'] += 1
                        continue
                    if fast:
                        report(index, len(paths), '建立快速索引', path)
                        quick = quick_fingerprint(path)
                        if self.confirm_duplicate(path, quick, stat, lambda text: report(index, len(paths), text, path), cancelled):
                            results['duplicates'] += 1
                            continue
                        digest = 'fast-' + uuid.uuid4().hex
                        duration = 0
                    else:
                        report(index, len(paths), '计算指纹 0%', path)
                        digest = fingerprint(path, lambda done, total: report(index, len(paths), f'计算指纹 {done * 100 // max(1, total)}%', path, False), cancelled)
                        if self.db.execute('SELECT 1 FROM files WHERE digest=?', (digest,)).fetchone() or self.confirm_duplicate(path, quick_fingerprint(path), stat, lambda text: report(index,len(paths),text,path), cancelled):
                            results['duplicates'] += 1
                            continue
                        report(index, len(paths), '分析媒体', path)
                        duration = probe(path, cancelled=cancelled) if cancelled else probe(path)
                    parsed = parse_name(path, kind)
                    if kind == 'vr':
                        parsed.update(title=group['folder'].name)
                    if kind == 'series':
                        group = series_plan.group(path)
                        year = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', group['folder'].name)
                        parsed.update(title=group['folder'].name, year=int(year.group()) if year else None,
                                      season=series_plan.numbers[path][0], episode=series_plan.numbers[path][1])
                    if local['work']:
                        parsed.update({k:v for k,v in local['work']['metadata'].items() if k in {'title','year'}})
                    key = group['key'] if kind in {'series','vr'} else identity(parsed['title'], parsed['year'], kind) if kind != 'other' else 'file:' + digest
                    cover = self.directory / 'cache' / (digest + '.jpg')
                    try:
                        if not fast and not cover.exists():
                            report(index, len(paths), '生成缩略图', path)
                            thumbnail(path, cover, duration, cancelled=cancelled) if cancelled else thumbnail(path, cover, duration)
                    except ImportCancelled:
                        raise
                    except Exception as exc:
                        results['warnings'].append({'path': str(path), 'reason': '缩略图: ' + str(exc)})
                    with self.db:
                        known = self.db.execute('SELECT work_id FROM name_keys WHERE key=?', (key,)).fetchone()
                        if kind in {'series','vr'} and not known and group['known'] is not None: known = (group['known'],)
                        linked = set()
                        for namespace,value in (local['work'] or {}).get('metadata',{}).get('external_ids',{}).items():
                            row = self.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?',(kind,namespace,value)).fetchone()
                            if row: linked.add(row[0])
                        if len(linked)>1 or linked and known and known[0] not in linked:
                            raise ValueError('NFO 外部标识与已有作品冲突，请人工核对')
                        if kind == 'vr' and linked and not known:
                            raise ValueError('NFO 外部标识已关联其他目录，请人工核对后合并')
                        if linked: known = (next(iter(linked)),)

                        if known:
                            work_id = known[0]
                        else:
                            self.db.execute('INSERT OR IGNORE INTO works(identity,kind,title,year,added,thumbnail) VALUES (?,?,?,?,?,?)',
                                            (key, kind, parsed['title'], parsed['year'], now(), str(cover) if cover.exists() else None))
                            work_id = self.db.execute('SELECT id FROM works WHERE identity=?', (key,)).fetchone()[0]
                            self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)', (key,work_id))
                        if kind in {'series','vr'}:
                            self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)', (key,work_id))
                            if kind == 'series':self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)', (identity(parsed['title'],parsed['year'],kind),work_id))
                            group['known'] = work_id
                        if cover.exists():
                            self.db.execute('UPDATE works SET thumbnail=COALESCE(thumbnail,?) WHERE id=?', (str(cover),work_id))
                        self.db.execute('INSERT INTO files(work_id,path,digest,root,season,episode,duration) VALUES (?,?,?,?,?,?,?)',
                                        (work_id, str(path), digest, str(root), parsed['season'], parsed['episode'], duration))
                        file_id = self.db.execute('SELECT id FROM files WHERE path=?',(str(path),)).fetchone()[0]
                        if fast:
                            self.db.execute('INSERT INTO import_cache VALUES (?,?,?,?,?,?,?)', (file_id,stat.st_size,stat.st_mtime_ns,quick,None,signature,1))
                        if local['work'] or local['entry'] or local['poster'] or local.get('backdrop'):
                            nfo.apply(self,work_id,file_id,local,not bool(known),True,root,results['warnings'])

                    results['imported'] += 1
                except ImportCancelled:
                    file_finished = False
                    raise
                except Exception as exc:
                    results['errors'].append({'path': str(path), 'reason': str(exc)})
                finally:
                    report(index + int(file_finished), len(paths), f"已处理 · 导入 {results['imported']} · 重复 {results['duplicates']} · 失败 {len(results['errors'])} · 警告 {len(results['warnings'])}", path)
            report(len(paths), len(paths), '处理完成' if paths else '没有找到视频')
            self.task(task_id, 'import', 'partial' if results['errors'] else 'done', payload, results)
        except ImportCancelled:
            results['cancelled'] = True
            self.task(task_id, 'import', 'cancelled', payload, results)
        except Exception as exc:
            self.task(task_id, 'import', 'failed', payload, results, str(exc))
            raise
        return results

    def index_legacy_files(self, progress, cancelled=None):
        # Upgrade existing libraries lazily without reading whole videos.
        rows = self.db.execute('SELECT f.* FROM files f LEFT JOIN import_cache c ON c.file_id=f.id WHERE c.file_id IS NULL').fetchall()
        for index, file in enumerate(rows):
            check_cancelled(cancelled)
            try:
                path = Path(file['path']); stat = path.stat()
                progress(f'建立旧库快速索引 {index+1} / {len(rows)}')
                quick = quick_fingerprint(path)
                # Old digests may refer to replaced files: verify before trusting.
                with self.db:
                    self.db.execute('INSERT OR IGNORE INTO import_cache VALUES (?,?,?,?,?,?,?)', (file['id'],stat.st_size,stat.st_mtime_ns,quick,None,'',0))
            except OSError:
                continue

    def confirm_duplicate(self, path, quick, stat, progress, cancelled=None):
        candidates = self.db.execute('SELECT c.*,f.path FROM import_cache c JOIN files f ON f.id=c.file_id WHERE c.quick=? AND c.size=?', (quick,stat.st_size)).fetchall()
        incoming = None
        for candidate in candidates:
            other = Path(candidate['path'])
            try:
                previous = other.stat()
                if previous.st_size != candidate['size'] or previous.st_mtime_ns != candidate['modified']:
                    continue
                progress('疑似重复，完整校验')
                incoming = incoming or fingerprint(path, cancelled=cancelled)
                full = candidate['full'] or fingerprint(other, cancelled=cancelled)
                current = other.stat()
                if (current.st_size,current.st_mtime_ns) != (previous.st_size,previous.st_mtime_ns):
                    continue
                with self.db:
                    self.db.execute('UPDATE import_cache SET full=? WHERE file_id=?', (full,candidate['file_id']))
                after = path.stat()
                if (after.st_size,after.st_mtime_ns) != (stat.st_size,stat.st_mtime_ns):
                    raise ValueError('导入期间文件已变化，请稍后重试')
                if full == incoming:
                    return True
            except OSError:
                continue
        return False

    def enrich_pending(self, progress=None, limit=1, cancelled=None):
        """Durable queue: metadata becomes visible before expensive media work."""
        rows = self.db.execute('SELECT f.*,c.size,c.modified,c.pending FROM files f JOIN import_cache c ON c.file_id=f.id WHERE c.pending IN (1,2) ORDER BY f.id LIMIT ?', (limit,)).fetchall()
        result = {'completed':0,'errors':[]}
        for index, file in enumerate(rows):
            task_id = 'media-' + str(file['id'])
            payload = {'file_id':file['id'],'path':file['path']}
            self.task(task_id, 'media', 'running', payload)
            try:
                check_cancelled(cancelled)
                path = Path(file['path']); before = path.stat()
                if (before.st_size,before.st_mtime_ns) != (file['size'],file['modified']):
                    raise ValueError('文件已变化，请重新导入目录')
                if progress: progress(index,len(rows),'补充媒体时长 · '+file['path'])
                duration = probe(path, cancelled=cancelled) if cancelled else probe(path)
                work = self.work(file['work_id'])
                cover = self.directory / 'cache' / (file['digest'] + '.jpg')
                # Existing posters are ready to use; do not decode a frame again.
                if file['pending'] == 2 or self.setting('view_mode') == 'thumbnail' or not work['thumbnail'] or not Path(work['thumbnail']).is_file():
                    if progress: progress(index,len(rows),'生成缺失缩略图 · '+file['path'])
                    thumbnail(path, cover, duration, cancelled=cancelled) if cancelled else thumbnail(path, cover, duration)
                after = path.stat()
                if (after.st_size,after.st_mtime_ns) != (before.st_size,before.st_mtime_ns):
                    raise ValueError('分析期间文件已变化，请重新导入目录')
                with self.db:
                    self.db.execute('UPDATE files SET duration=?,position=MIN(position,?) WHERE id=?',(duration,duration,file['id']))
                    if cover.exists() and 'poster' not in work['locked'] and not work['metadata'].get('nfo_poster'):
                        self.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(cover),file['work_id']))
                    self.db.execute('UPDATE import_cache SET pending=0 WHERE file_id=?',(file['id'],))
                result['completed'] += 1
                self.task(task_id,'media','done',payload)
            except ImportCancelled:
                result['cancelled'] = True
                self.task(task_id,'media','cancelled',payload)
                break
            except Exception as exc:
                result['errors'].append({'path':file['path'],'reason':str(exc)})
                with self.db:
                    self.db.execute('UPDATE import_cache SET pending=-1 WHERE file_id=?',(file['id'],))
                self.task(task_id,'media','failed',payload,error=str(exc))
            if progress: progress(index+1,len(rows),'后台媒体处理完成 · '+file['path'])
        return result

    def task(self, task_id, kind, status, payload, result=None, error=None):
        parent=getattr(self,'parent_task_id',None)
        if parent and parent!=task_id:payload={**payload,'parent_task_id':parent}
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?)',
                            (task_id, kind, status, json.dumps(payload, ensure_ascii=False), json.dumps(result or {}, ensure_ascii=False), error, now()))

    def query(self, filters=None, offset=0, limit=None):
        f = filters or {}
        clauses, args = ['1=1'], []
        if 'kinds' in f and not f['kinds']:
            return []
        if 'ids' in f:
            if not f['ids']:
                return []
            clauses.append('id IN (' + ','.join('?' for _ in f['ids']) + ')')
            args.extend(f['ids'])
        if f.get('kinds'):
            clauses.append('kind IN (' + ','.join('?' for _ in f['kinds']) + ')')
            args.extend(f['kinds'])
        for field, operator in [('year_min', '>='), ('year_max', '<='), ('rating_min', '>='), ('rating_max', '<=')]:
            if f.get(field) is not None:
                clauses.append(f'{field.split("_")[0]} {operator} ?')
                args.append(f[field])
        for field in ['favorite', 'watchlist', 'disliked']:
            if field in f:
                clauses.append(f'{field}=?')
                args.append(int(f[field]))
        if f.get('local', True):
            clauses.append('EXISTS(SELECT 1 FROM files WHERE work_id=works.id)')
        rows = self.db.execute('SELECT * FROM works WHERE ' + ' AND '.join(clauses) + ' ORDER BY added DESC,id DESC', args).fetchall()
        ids = {row['id'] for row in rows}
        files, sources, watches = {}, {}, {}
        # Batch joins avoid N+1 queries while preserving complete-result filtering and shuffle.
        for row in self.db.execute('SELECT * FROM files WHERE work_id IN (SELECT id FROM works WHERE '+ ' AND '.join(clauses)+') ORDER BY season,episode,path',args):
            if row['work_id'] in ids:
                files.setdefault(row['work_id'], []).append(dict(row))
        for row in self.db.execute('SELECT * FROM sources WHERE work_id IN (SELECT id FROM works WHERE '+' AND '.join(clauses)+')',args):
            if row['work_id'] in ids:
                sources.setdefault(row['work_id'], []).append(dict(row))
        for row in self.db.execute('SELECT f.work_id,SUM(s.watched) FROM sessions s JOIN files f ON f.id=s.file_id WHERE f.work_id IN (SELECT id FROM works WHERE '+' AND '.join(clauses)+') GROUP BY f.work_id',args):
            watches[row[0]] = row[1]
        items = []
        for row in rows:
            item = dict(row)
            item['metadata'] = actor_defaults(json.loads(item['metadata']), item['kind'])
            item['liked'] = item['favorite']
            item['locked'] = json.loads(item['locked'])
            item['files'] = files.get(item['id'], [])
            if item['kind'] in {'fans','vr'}:
                from .series import natural_key
                item['files'].sort(key=lambda file:natural_key(file['path']))
            for file in item['files']:
                details=item['metadata'].get('episode_details',{}).get(str(file['id']),{})
                file.update({key:details[key] for key in ['title','overview'] if key in details})
                file['stills']=item['metadata'].get('episode_stills',{}).get(str(file['id']),[])
            item['sources'] = sources.get(item['id'], [])
            m = item['metadata']
            q = f.get('query', '').casefold().strip()
            haystack = ' '.join([item['title'], *m.get('aliases', []), *[x['path'] for x in item['files']]]).casefold()
            if q and q not in haystack:
                continue
            if f.get('continue') and not any(x['position'] > 0 and not x['completed'] for x in item['files']):
                continue
            if f.get('female_cast') and not any(a.get('gender') == 'female' for a in m.get('actors', [])):
                continue
            tags = set(m.get('tags', []))
            if f.get('tags_all') and not set(f['tags_all']) <= tags:
                continue
            if f.get('tags_any') and not tags.intersection(f['tags_any']):
                continue
            if tags.intersection(f.get('tags_not', [])):
                continue
            if f.get('folder') and not any(Path(x['path']).is_relative_to(Path(f['folder'])) for x in item['files']):
                continue
            if f.get('actor') and not any(f['actor'] in [a.get('name'), *a.get('aliases', [])] for a in m.get('actors', [])):
                continue
            watched = watches.get(item['id'], 0)
            seen = watched > 0 or any(file['completed'] or file['position'] > 0 for file in item['files'])
            if f.get('watched') == 'yes' and not seen or f.get('watched') == 'no' and seen:
                continue
            item['watch_state'] = watch_state(item['files'])
            if f.get('watch_state') and item['watch_state'] != f['watch_state']:
                continue
            item['watched'] = watched
            items.append(item)
        items = sort_items(items, f.get('sort', 'added'), f.get('descending', True))
        return items[offset:offset + limit if limit is not None else None]

    def filter_options(self, kinds=None, local=True):
        """Full catalog facets without loading video files, images or watch history."""
        tags, actors, years = set(), set(), set()
        sql = 'SELECT kind,year,metadata FROM works'
        if local:
            sql += ' WHERE EXISTS(SELECT 1 FROM files WHERE work_id=works.id)'
        for row in self.db.execute(sql):
            if kinds is not None and row['kind'] not in kinds:
                continue
            metadata = json.loads(row['metadata'])
            tags.update(metadata.get('tags', []))
            for actor in metadata.get('actors', []):
                actors.update([actor['name'], *actor.get('aliases', [])])
            if row['year']:
                years.add(row['year'])
        return {'tags': sorted(tags, key=str.casefold), 'actors': sorted(actors, key=str.casefold),
                'years': sorted(years, reverse=True)}

    def shuffle(self, filters):
        filters = {**filters, 'local': True}
        ids = [w['id'] for w in self.query(filters)]
        random.SystemRandom().shuffle(ids)
        queue = {'ids': ids, 'index': 0, 'filters': filters}
        self.set_setting('queue', queue)
        return queue

    def queue_step(self, delta=0):
        queue = self.setting('queue', {'ids': [], 'index': 0})
        index = queue['index'] + delta
        if queue.get('repeat') == 'all' and queue['ids']: index %= len(queue['ids'])
        queue['index'] = max(0, min(len(queue['ids']), index))
        self.set_setting('queue', queue)
        return queue['ids'][queue['index']] if queue['index'] < len(queue['ids']) else None

    def resume_file(self, work_id):
        files = self.work(work_id)['files']
        if not files:
            raise ValueError('该影片未入库')
        unfinished = [f for f in files if not f['completed']]
        return next((f for f in unfinished if f['position'] > 0), None) or next(iter(unfinished), files[0])

    def actresses(self, minimum=0, order='average'):
        actors = {}
        # Stable external IDs and overlapping aliases merge identities; movie actors with unknown gender use the female default.
        for item in self.query({'kinds': ['movie']}):
            for actor in item['metadata'].get('actors', []):
                if actor.get('gender') != 'female':
                    continue
                names = {str(n).casefold() for n in [actor['name'], *actor.get('aliases', [])]}
                key = actor.get('id') or actor['name'].casefold()
                matches = [k for k, a in actors.items() if k == key or a['_names'] & names]
                record = actors.setdefault(matches[0] if matches else key, {**actor, '_names': set(), '_works': {}})
                # An earlier locked/missing-photo credit must not hide a cached
                # portrait found on another matching credit of this actress.
                if not record.get('photo_cache') and actor.get('photo_cache'):
                    for field in ('photo', 'photo_cache', 'photo_revision', 'photo_source', 'photo_source_id', 'photo_source_url', 'photo_page', 'photo_license', 'photo_attribution'):
                        if field in actor: record[field] = actor[field]
                for old in matches[1:]:
                    record['_names'].update(actors[old]['_names'])
                    record['_works'].update(actors.pop(old)['_works'])
                record['_names'].update(names)
                record['_works'][item['id']] = item
        result = []
        for a in actors.values():
            ratings = [w['rating'] for w in a['_works'].values() if w['rating'] is not None]
            if len(ratings) < minimum:
                continue
            a.update(count=len(a['_works']), rated=len(ratings), average=sum(ratings) / len(ratings) if ratings else None,
                     work_ids=list(a['_works']), portrait_names=sorted(a['_names']))
            del a['_names'], a['_works']
            result.append(a)
        return sorted(result, key=lambda a: a['name'].casefold() if order == 'name' else -(a.get(order) if a.get(order) is not None else -1))

    def recommendations(self, discovered=False, items=None):
        all_items = self.query({'local': False}) if items is None else items
        all_items = [work for work in all_items if work['kind']!='fans']
        weights = Counter()
        for w in all_items:
            rating = (w['rating'] - 5.5) * 3 if w['rating'] is not None else 0
            strength = rating + w['favorite'] * 4 + w['watchlist'] * 2 - w['disliked'] * 20 + min(w['watched'] / 3600, 1)
            features = ['标签:' + t for t in w['metadata'].get('tags', [])]
            features += ['演员:' + a['name'] for a in w['metadata'].get('actors', []) if a.get('gender') == 'female']
            for feature in set(features):
                weights[feature] += strength
        result = []
        for w in all_items:
            if w['kind'] == 'other' or w['disliked'] or bool(w['files']) == discovered:
                continue
            features = ['标签:' + t for t in w['metadata'].get('tags', [])]
            features += ['演员:' + a['name'] for a in w['metadata'].get('actors', []) if a.get('gender') == 'female']
            contributions = sorted([(feature, weights[feature]) for feature in set(features)], key=lambda pair: -pair[1])
            score = sum(v for _, v in contributions) + w['watchlist'] * 2
            reasons = [f'{k}（偏好 {v:+.1f}）' for k, v in contributions if v > 0][:3]
            w.update(score=score, reasons=reasons or ['探索尚未建立偏好的作品'])
            result.append(w)
        result.sort(key=lambda w: (-w['score'], w['id']))
        # Every fifth slot is reserved for deterministic unfamiliar-content exploration.
        explorers = [w for w in result if not w['score'] and not w['watched']]
        if len(result) > 4 and explorers:
            candidate = explorers[0]
            result.remove(candidate)
            result.insert(4, candidate)
        return result

    def stats(self):
        sessions = [dict(r) for r in self.db.execute('SELECT s.*,f.work_id,w.kind,w.title FROM sessions s JOIN files f ON f.id=s.file_id JOIN works w ON w.id=f.work_id')]
        result = {'sessions': len(sessions), 'valid': sum(s['watched'] > 600 for s in sessions),
                  'seconds': sum(s['watched'] for s in sessions), 'movies': len({s['work_id'] for s in sessions if s['kind'] == 'movie' and s['watched'] > 0}),
                  'series': len({s['work_id'] for s in sessions if s['kind'] == 'series' and s['watched'] > 0}),
                  'days': Counter(), 'weeks': Counter(), 'months': Counter(), 'years': Counter(),
                  'ratings': Counter(), 'tags': Counter(), 'actors': Counter(), 'directors': Counter(), 'types': Counter(), 'repeat': Counter()}
        for row in self.db.execute('SELECT day,SUM(watched) FROM activity GROUP BY day'):
            day, seconds = row
            date = datetime.fromisoformat(day)
            result['days'][day] += seconds
            result['weeks'][f'{date.isocalendar().year}-W{date.isocalendar().week:02}'] += seconds
            result['months'][day[:7]] += seconds
            result['years'][day[:4]] += seconds
        for w in self.query():
            if w['rating'] is not None:
                result['ratings'][str(w['rating'])] += 1
            seconds = w['watched']
            result['types'][w['kind']] += seconds
            for tag in set(w['metadata'].get('tags', [])):
                result['tags'][tag] += seconds
            for a in w['metadata'].get('actors', []):
                result['actors'][a['name']] += seconds
            for d in w['metadata'].get('directors', []):
                result['directors'][d] += seconds
        for s in sessions:
            if s['watched'] > 600:
                result['repeat'][s['title']] += 1
        return result

    def annual_report(self, year):
        prefix = str(int(year)) + '-%'
        rows = [dict(r) for r in self.db.execute("""SELECT s.id,s.watched AS session_watched,f.work_id,w.kind,w.title,w.metadata,SUM(a.watched) AS watched
            FROM activity a JOIN sessions s ON s.id=a.session_id JOIN files f ON f.id=s.file_id JOIN works w ON w.id=f.work_id
            WHERE a.day LIKE ? GROUP BY s.id""", (prefix,))]
        tags, titles = Counter(), Counter()
        for row in rows:
            titles[row['title']] += row['watched']
            for tag in json.loads(row['metadata']).get('tags', []):
                tags[tag] += row['watched']
        return {'year': int(year), 'seconds':sum(r['watched'] for r in rows), 'sessions':len(rows),
                'valid':sum(r['session_watched']>600 for r in rows), 'distinct':len({r['work_id'] for r in rows}),
                'movies':len({r['work_id'] for r in rows if r['kind']=='movie'}),
                'series':len({r['work_id'] for r in rows if r['kind']=='series'}),'tags':tags,'titles':titles}

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError('备份文件已存在，请选择新名称')
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
        finally:
            target.close()


class WatchSession:
    """Accumulate monotonic elapsed time only while playback position advances normally."""
    def __init__(self, library, file_id, clock=time.monotonic):
        self.library, self.file_id, self.clock = library, file_id, clock
        self.id = uuid.uuid4().hex
        self.last_time, self.last_position = clock(), None
        self.playing = False
        self.closed = False
        with library.db:
            library.db.execute('INSERT INTO sessions(id,file_id,started) VALUES (?,?,?)', (self.id, file_id, now()))

    def tick(self, position, playing, rate=1.0, seeking=False):
        if self.closed:
            return
        current = self.clock()
        elapsed = current - self.last_time
        watched = 0.0
        if self.playing and playing and not seeking and self.last_position is not None and 0 < elapsed <= 3:
            advance = position - self.last_position
            if 0 < advance <= elapsed * rate + .6:
                watched = min(elapsed, advance / max(rate, .1))
        with self.library.db:
            self.library.db.execute('UPDATE sessions SET watched=watched+? WHERE id=?', (watched, self.id))
            if watched:
                self.library.db.execute('INSERT INTO activity VALUES (?,?,?) ON CONFLICT(session_id,day) DO UPDATE SET watched=watched+excluded.watched',
                                        (self.id, datetime.now().date().isoformat(), watched))
            self.library.db.execute('UPDATE files SET position=? WHERE id=?', (max(0, position), self.file_id))
        self.last_time, self.last_position, self.playing = current, position, playing

    def finish(self):
        if not self.closed:
            with self.library.db:
                self.library.db.execute('UPDATE sessions SET ended=? WHERE id=?', (now(), self.id))
            self.closed = True
