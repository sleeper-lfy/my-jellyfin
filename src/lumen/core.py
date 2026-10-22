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


def now():
    return datetime.now(timezone.utc).isoformat()


def data_directory():
    return Path(os.environ.get('LUMEN_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'Lumen')


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def parse_name(path, kind):
    stem = Path(path).stem
    episode = re.search(r'(?i)(?:s(\d{1,2})[ ._-]*e(\d{1,3})|(\d{1,2})x(\d{1,3}))', stem)
    year_match = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', stem)
    end = min([m.start() for m in (episode, year_match) if m] or [len(stem)])
    title = re.sub(r'[._]+', ' ', stem[:end]).strip(' -[]()') or stem
    season, number = (int(episode.group(1) or episode.group(3)), int(episode.group(2) or episode.group(4))) if episode else (1, 1)
    if kind == 'series' and not episode:
        season_match = re.search(r'(?i)(?:season|s|第)\s*(\d{1,2})', Path(path).parent.name)
        number_match = re.match(r'(?i)(?:e|ep|第)?\s*(\d{1,3})(?:\D|$)', stem)
        if not number_match:
            raise ValueError('未识别季集编号，请使用 剧名.S01E01 格式或 Season 1/01 标题 格式')
        season, number = int(season_match.group(1)) if season_match else 1, int(number_match.group(1))
        title = Path(path).parent.parent.name if season_match else Path(path).parent.name
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


def probe(path):
    executable = tool('ffprobe')
    if not executable:
        raise RuntimeError('未找到 ffprobe，请在设置说明中配置 FFmpeg PATH')
    result = subprocess.run([executable, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                            capture_output=True, timeout=45, check=True, creationflags=0x08000000 if os.name == 'nt' else 0)
    info = json.loads(result.stdout)
    if not any(s.get('codec_type') == 'video' for s in info.get('streams', [])):
        raise ValueError('文件不含视频流')
    return float(info.get('format', {}).get('duration', 0))


def thumbnail(path, target, duration, at=None):
    executable = tool('ffmpeg')
    if not executable:
        raise RuntimeError('未找到 ffmpeg')
    second = at if at is not None else min(max(duration * .15, 0), 300)
    subprocess.run([executable, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(second), '-i', str(path),
                    '-frames:v', '1', '-vf', 'scale=480:-2', str(target)], capture_output=True, check=True, timeout=60,
                   creationflags=0x08000000 if os.name == 'nt' else 0)
    if not Path(target).is_file():
        raise RuntimeError('未能生成缩略图')


class Library:
    def __init__(self, directory=None):
        self.directory = Path(directory or data_directory())
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / 'cache').mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.directory / 'library.sqlite', timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS works (
          id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
          title TEXT NOT NULL, year INTEGER, metadata TEXT NOT NULL DEFAULT '{}',
          rating INTEGER CHECK(rating BETWEEN 1 AND 10), favorite INTEGER NOT NULL DEFAULT 0,
          watchlist INTEGER NOT NULL DEFAULT 0, disliked INTEGER NOT NULL DEFAULT 0,
          locked TEXT NOT NULL DEFAULT '[]', added TEXT NOT NULL, discovered TEXT, thumbnail TEXT);
        CREATE TABLE IF NOT EXISTS files (
          id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES works(id), path TEXT UNIQUE NOT NULL,
          digest TEXT NOT NULL, root TEXT NOT NULL, season INTEGER, episode INTEGER,
          duration REAL NOT NULL, position REAL NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS files_work ON files(work_id);
        CREATE INDEX IF NOT EXISTS files_digest ON files(digest);
        CREATE INDEX IF NOT EXISTS works_kind ON works(kind,year);
        CREATE TABLE IF NOT EXISTS sources (
          work_id INTEGER REFERENCES works(id), plugin TEXT NOT NULL, site TEXT NOT NULL,
          source_id TEXT NOT NULL, url TEXT NOT NULL, updated TEXT NOT NULL, site_added TEXT,
          rating REAL, UNIQUE(plugin,source_id));
        CREATE TABLE IF NOT EXISTS name_keys (key TEXT PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES works(id));
        CREATE TABLE IF NOT EXISTS external_ids (kind TEXT NOT NULL, namespace TEXT NOT NULL, value TEXT NOT NULL, work_id INTEGER NOT NULL REFERENCES works(id), UNIQUE(kind,namespace,value));
        INSERT OR IGNORE INTO name_keys SELECT identity,id FROM works;
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, file_id INTEGER REFERENCES files(id), started TEXT NOT NULL,
          ended TEXT, watched REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS activity (
          session_id TEXT REFERENCES sessions(id), day TEXT NOT NULL, watched REAL NOT NULL,
          PRIMARY KEY(session_id,day));
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
          result TEXT NOT NULL DEFAULT '{}', error TEXT, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lists (name TEXT PRIMARY KEY, filters TEXT NOT NULL);
        ''')
        self.db.commit()

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
        item['metadata'] = json.loads(item['metadata'])
        item['locked'] = json.loads(item['locked'])
        item['files'] = [dict(r) for r in self.db.execute('SELECT * FROM files WHERE work_id=? ORDER BY season,episode,path', (work_id,))]
        item['sources'] = [dict(r) for r in self.db.execute('SELECT * FROM sources WHERE work_id=?', (work_id,))]
        return item

    def update_personal(self, work_id, **fields):
        allowed = {'rating', 'favorite', 'watchlist', 'disliked'}
        if not fields or not fields.keys() <= allowed:
            raise ValueError('无效个人字段')
        if 'rating' in fields and fields['rating'] is not None and (type(fields['rating']) is not int or not 1 <= fields['rating'] <= 10):
            raise ValueError('个人评分须为 1–10 整数或空')
        with self.db:
            self.db.execute('UPDATE works SET ' + ','.join(f'{key}=?' for key in fields) + ' WHERE id=?', (*fields.values(), work_id))

    def merge_works(self, source_id, target_id, commit=True):
        if source_id == target_id:
            return target_id
        source, target = self.work(source_id), self.work(target_id)
        if source['kind'] != target['kind'] or source['kind'] == 'other':
            raise ValueError('仅可合并相同类型的电影或电视剧')
        merged = {**source['metadata'], **target['metadata']}
        merged['aliases'] = list(dict.fromkeys(source['metadata'].get('aliases',[]) + target['metadata'].get('aliases',[]) + ([source['title']] if source['title'] != target['title'] else [])))
        merged['external_ids'] = {**source['metadata'].get('external_ids',{}), **target['metadata'].get('external_ids',{})}
        with self.db if commit else nullcontext():
            self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(source['identity'],source_id))
            self.db.execute('UPDATE files SET work_id=? WHERE work_id=?', (target_id, source_id))
            self.db.execute('UPDATE sources SET work_id=? WHERE work_id=?', (target_id, source_id))
            self.db.execute('UPDATE works SET metadata=?,rating=?,favorite=?,watchlist=?,disliked=?,discovered=?,thumbnail=? WHERE id=?',
                (json.dumps(merged, ensure_ascii=False), target['rating'] if target['rating'] is not None else source['rating'],
                 max(target['favorite'],source['favorite']),max(target['watchlist'],source['watchlist']),max(target['disliked'],source['disliked']),
                 min([d for d in [target['discovered'],source['discovered']] if d] or [None]),target['thumbnail'] or source['thumbnail'],target_id))
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

    def import_folder(self, root, kind, progress=None):
        if kind not in {'movie', 'series', 'other'}:
            raise ValueError('无效媒体类型')
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError('请选择文件夹')
        task_id = uuid.uuid4().hex
        payload = {'root': str(root), 'kind': kind}
        self.task(task_id, 'import', 'running', payload)
        results = {'imported': 0, 'duplicates': 0, 'errors': [], 'warnings': []}
        try:
            paths = sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() in VIDEO_EXTENSIONS and root in p.resolve().parents)
            for index, path in enumerate(paths):
                try:
                    if self.db.execute('SELECT 1 FROM files WHERE path=?', (str(path),)).fetchone():
                        results['duplicates'] += 1
                        continue
                    digest = fingerprint(path)
                    if self.db.execute('SELECT 1 FROM files WHERE digest=?', (digest,)).fetchone():
                        results['duplicates'] += 1
                        continue
                    duration = probe(path)
                    parsed = parse_name(path, kind)
                    key = identity(parsed['title'], parsed['year'], kind) if kind != 'other' else 'file:' + digest
                    cover = self.directory / 'cache' / (digest + '.jpg')
                    try:
                        if not cover.exists():
                            thumbnail(path, cover, duration)
                    except Exception as exc:
                        results['warnings'].append({'path': str(path), 'reason': '缩略图: ' + str(exc)})
                    with self.db:
                        known = self.db.execute('SELECT work_id FROM name_keys WHERE key=?', (key,)).fetchone()
                        if known:
                            work_id = known[0]
                        else:
                            self.db.execute('INSERT OR IGNORE INTO works(identity,kind,title,year,added,thumbnail) VALUES (?,?,?,?,?,?)',
                                            (key, kind, parsed['title'], parsed['year'], now(), str(cover) if cover.exists() else None))
                            work_id = self.db.execute('SELECT id FROM works WHERE identity=?', (key,)).fetchone()[0]
                            self.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)', (key,work_id))
                        if cover.exists():
                            self.db.execute('UPDATE works SET thumbnail=COALESCE(thumbnail,?) WHERE id=?', (str(cover),work_id))
                        self.db.execute('INSERT INTO files(work_id,path,digest,root,season,episode,duration) VALUES (?,?,?,?,?,?,?)',
                                        (work_id, str(path), digest, str(root), parsed['season'], parsed['episode'], duration))
                    results['imported'] += 1
                except Exception as exc:
                    results['errors'].append({'path': str(path), 'reason': str(exc)})
                finally:
                    self.task(task_id, 'import', 'running', payload, results)
                    if progress:
                        progress(index + 1, len(paths), str(path))
            self.task(task_id, 'import', 'partial' if results['errors'] else 'done', payload, results)
        except Exception as exc:
            self.task(task_id, 'import', 'failed', payload, results, str(exc))
            raise
        return results

    def task(self, task_id, kind, status, payload, result=None, error=None):
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
        for row in self.db.execute('SELECT * FROM files ORDER BY season,episode,path'):
            if row['work_id'] in ids:
                files.setdefault(row['work_id'], []).append(dict(row))
        for row in self.db.execute('SELECT * FROM sources'):
            if row['work_id'] in ids:
                sources.setdefault(row['work_id'], []).append(dict(row))
        for row in self.db.execute('SELECT f.work_id,SUM(s.watched) FROM sessions s JOIN files f ON f.id=s.file_id GROUP BY f.work_id'):
            watches[row[0]] = row[1]
        items = []
        for row in rows:
            item = dict(row)
            item['metadata'] = json.loads(item['metadata'])
            item['locked'] = json.loads(item['locked'])
            item['files'] = files.get(item['id'], [])
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
            if f.get('watched') == 'yes' and watched <= 0 or f.get('watched') == 'no' and watched > 0:
                continue
            item['watched'] = watched
            items.append(item)
        return items[offset:offset + limit if limit is not None else None]

    def shuffle(self, filters):
        filters = {**filters, 'local': True}
        ids = [w['id'] for w in self.query(filters)]
        random.SystemRandom().shuffle(ids)
        queue = {'ids': ids, 'index': 0, 'filters': filters}
        self.set_setting('queue', queue)
        return queue

    def queue_step(self, delta=0):
        queue = self.setting('queue', {'ids': [], 'index': 0})
        queue['index'] = max(0, min(len(queue['ids']), queue['index'] + delta))
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
        # Stable external IDs and overlapping aliases merge identities; unknown genders never imply female.
        for item in self.query({'kinds': ['movie']}):
            for actor in item['metadata'].get('actors', []):
                if actor.get('gender') != 'female':
                    continue
                names = {str(n).casefold() for n in [actor['name'], *actor.get('aliases', [])]}
                key = actor.get('id') or actor['name'].casefold()
                matches = [k for k, a in actors.items() if k == key or a['_names'] & names]
                record = actors.setdefault(matches[0] if matches else key, {**actor, '_names': set(), '_works': {}})
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
                     work_ids=list(a['_works']))
            del a['_names'], a['_works']
            result.append(a)
        return sorted(result, key=lambda a: a['name'].casefold() if order == 'name' else -(a.get(order) if a.get(order) is not None else -1))

    def recommendations(self, discovered=False):
        all_items = self.query({'local': False})
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
