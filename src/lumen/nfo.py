"""Read local Jellyfin/Kodi sidecars without network access or modifying originals."""
from pathlib import Path
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET

MAX_NFO = 2_000_000


def sibling(folder, name):
    return next((p for p in folder.iterdir() if p.name.casefold() == name.casefold() and p.is_file() and not p.is_symlink()), None)


def read(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_NFO + 1)
    if len(data) > MAX_NFO:
        raise ValueError('NFO 超过 2 MB')
    # Reject DTDs also in UTF-16/32; ElementTree must never expand user entities.
    if re.search(br'<!\s*(DOCTYPE|ENTITY)', data.replace(b'\x00', b''), re.I):
        raise ValueError('NFO 不允许 DTD 或实体声明')
    tree = ET.fromstring(data)
    if tree.tag not in {'movie', 'tvshow', 'episodedetails'}:
        raise ValueError('不支持的 NFO 根节点：' + tree.tag)
    def text(key): return (tree.findtext(key) or '').strip()
    def values(key): return list(dict.fromkeys(e.text.strip() for e in tree.findall(key) if e.text and e.text.strip()))
    def integer(key, low, high):
        value = text(key)
        if not value: return None
        number = int(value)
        if not low <= number <= high: raise ValueError('NFO 数值越界：' + key)
        return number
    metadata = {'title': text('title'), 'year': integer('year', 1800, 2200),
                'overview': text('plot') or text('outline'), 'aliases': values('originaltitle') + values('sorttitle'),
                'tags': list(dict.fromkeys(values('genre') + values('tag'))), 'directors': values('director'),
                'studios': values('studio'), 'released': text('premiered') or text('releasedate'),
                'content_rating': text('mpaa'), 'actors': [], 'external_ids': {}}
    for actor in tree.findall('actor'):
        name = (actor.findtext('name') or '').strip()
        if name:
            gender = (actor.findtext('gender') or 'unknown').strip().lower()
            metadata['actors'].append({'name': name, 'role': (actor.findtext('role') or '').strip(),
                                       'gender': gender if gender in {'female','male'} else 'unknown', 'aliases': []})
    for item in tree.findall('uniqueid'):
        namespace = item.get('type', '').lower().strip()
        value = (item.text or '').strip()
        if namespace and value: metadata['external_ids'][namespace] = value
    for field, namespace in [('imdbid','imdb'), ('imdb_id','imdb'), ('tmdbid','tmdb'), ('tvdbid','tvdb')]:
        if text(field): metadata['external_ids'].setdefault(namespace, text(field))
    if text('id').startswith('tt'): metadata['external_ids'].setdefault('imdb', text('id'))
    ratings = tree.findall('./ratings/rating')
    chosen = next((r for r in ratings if r.get('default','').lower() == 'true'), ratings[0] if ratings else None)
    rating = None
    value = chosen.findtext('value') if chosen is not None else text('rating')
    if value:
        maximum = float(chosen.get('max', '10')) if chosen is not None else 10
        if not math.isfinite(maximum) or maximum <= 0: raise ValueError('NFO 评分上限无效')
        rating = float(value) * 10 / maximum
        if not math.isfinite(rating) or not 0 <= rating <= 10: raise ValueError('NFO 评分无效')
    resume = tree.findtext('./resume/position')
    position = float(resume) if resume else None
    if position is not None and (not math.isfinite(position) or position < 0): raise ValueError('NFO 播放位置无效')
    return {'type': tree.tag, 'metadata': {k:v for k,v in metadata.items() if v not in (None, '', [], {})},
            'season': integer('season',0,999), 'episode': integer('episode',0,99999),
            'showtitle': text('showtitle'), 'rating': rating, 'userrating': integer('userrating',0,10),
            'completed': text('watched').lower() == 'true' or (integer('playcount',0,1000000) or 0) > 0,
            'position': position, 'thumbs': [(e.text or '').strip() for e in tree.findall('thumb') if e.get('aspect','poster') == 'poster'],
            'path': path}


def load(video, root, kind, warnings):
    """Invalid sidecars are warnings; filename import remains available."""
    def safe(path):
        if not path: return None
        try: return read(path)
        except (ValueError, OSError, ET.ParseError, ZeroDivisionError) as exc:
            warnings.append({'path': str(path), 'reason': 'NFO: ' + str(exc)})
            return None
    adjacent = sibling(video.parent, video.stem + '.nfo')
    show = None
    if kind == 'series':
        folder = video.parent
        while folder.is_relative_to(root):
            candidate = sibling(folder, 'tvshow.nfo')
            if candidate:
                show = safe(candidate)
                break
            if folder == root: break
            folder = folder.parent
    elif not adjacent:
        from .core import VIDEO_EXTENSIONS
        if sum(p.suffix.lower() in VIDEO_EXTENSIONS for p in video.parent.iterdir() if p.is_file()) == 1:
            adjacent = sibling(video.parent, 'movie.nfo')
    entry = safe(adjacent)
    expected = 'episodedetails' if kind == 'series' else 'movie'
    if entry and entry['type'] != expected:
        warnings.append({'path': str(adjacent), 'reason': 'NFO 类型与导入分区不一致'})
        entry = None
    if show and show['type'] != 'tvshow':
        warnings.append({'path': str(show['path']), 'reason': 'tvshow.nfo 根节点不是 tvshow'})
        show = None
    work = show if kind == 'series' else entry
    if kind == 'series' and not work and entry and entry['showtitle']:
        work = {**entry, 'metadata': {'title': entry['showtitle']}, 'rating': None, 'userrating': None, 'thumbs': []}
    return {'work': work, 'entry': entry, 'poster': poster(video, root, work, kind, warnings)}


def poster(video, root, work, kind, warnings):
    folder = work['path'].parent if work else video.parent
    candidates = []
    for value in (work or {}).get('thumbs', []):
        if value and not re.match(r'^[a-z]+:', value, re.I): candidates.append(folder / value)
    for name in [video.stem+'-poster.jpg', video.stem+'-poster.png', 'poster.jpg','poster.png','folder.jpg','folder.png']:
        candidate = sibling(folder, name)
        if candidate: candidates.append(candidate)
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink() and candidate.resolve().is_relative_to(root): return candidate
    return None


def cache_poster(path, directory):
    from PySide6.QtGui import QImageReader
    if path.stat().st_size > 20_000_000: raise ValueError('本地海报超过 20 MB')
    reader = QImageReader(str(path)); size = reader.size()
    if size.width() <= 0 or size.height() <= 0 or size.width()*size.height() > 40_000_000:
        raise ValueError('本地海报无效或像素过大')
    target = directory / 'cache' / ('nfo-' + hashlib.sha256(path.read_bytes()).hexdigest() + '.jpg')
    if not target.exists():
        from PySide6.QtCore import QSize
        if size.width() > 1000: reader.setScaledSize(QSize(1000, max(1, size.height()*1000//size.width())))
        image = reader.read()
        if image.isNull() or not image.save(str(target), 'JPEG'): raise ValueError('本地海报解码失败')
    return str(target)


def apply(library, work_id, file_id, data, fresh_work, fresh_file, root, warnings):
    from .core import now, identity
    item = library.work(work_id); metadata = item['metadata']; work = data['work']; entry = data['entry']
    if work:
        incoming = work['metadata']; fields = set(metadata.get('nfo_fields', []))
        external = incoming.get('external_ids', {})
        for namespace, value in external.items():
            linked = library.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?', (item['kind'],namespace,value)).fetchone()
            old = metadata.get('external_ids', {}).get(namespace)
            if linked and linked[0] != work_id or old and old != value:
                raise ValueError('NFO 外部标识冲突，未覆盖现有作品')
        for key, value in incoming.items():
            if key not in item['locked']:
                metadata[key] = {**metadata.get(key, {}), **value} if key == 'external_ids' else value
                fields.add(key)
        metadata['nfo_fields'] = sorted(fields)
        title = metadata.get('title', item['title']) if 'title' not in item['locked'] else item['title']
        year = metadata.get('year', item['year']) if 'year' not in item['locked'] else item['year']
        key = identity(title, year, item['kind'])
        linked = library.db.execute('SELECT work_id FROM name_keys WHERE key=?', (key,)).fetchone()
        if linked and linked[0] != work_id: raise ValueError('NFO 标题对应另一部作品，请人工核对后合并')
        library.db.execute('UPDATE works SET title=?,year=? WHERE id=?',(title,year,work_id))
        library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(key,work_id))
        for alias in metadata.get('aliases', []):
            library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(identity(alias,year,item['kind']),work_id))
        for namespace,value in external.items():
            library.db.execute('INSERT OR IGNORE INTO external_ids VALUES (?,?,?,?)',(item['kind'],namespace,value,work_id))
        source = hashlib.sha256(str(work['path'].resolve()).encode()).hexdigest()
        library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(plugin,source_id) DO UPDATE SET rating=excluded.rating,updated=excluded.updated',
                           (work_id,'local-nfo','本地 NFO',source,'',now(),None,work['rating']))
        if fresh_work and work.get('userrating'):
            library.db.execute('UPDATE works SET rating=? WHERE id=?',(work['userrating'],work_id))
    if entry and item['kind'] == 'series':
        metadata.setdefault('episode_details', {})[str(file_id)] = entry['metadata']
        if entry['season'] is not None and entry['episode'] is not None:
            library.db.execute('UPDATE files SET season=?,episode=? WHERE id=?',(entry['season'],entry['episode'],file_id))
    if fresh_file and entry:
        duration = library.db.execute('SELECT duration FROM files WHERE id=?',(file_id,)).fetchone()[0]
        position = min(entry['position'] or 0, duration)
        library.db.execute('UPDATE files SET position=?,completed=? WHERE id=?',(0 if entry['completed'] else position,int(entry['completed']),file_id))
    if data['poster'] and 'poster' not in item['locked']:
        try:
            cover = cache_poster(data['poster'],library.directory)
            library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(cover,work_id))
            metadata['nfo_poster'] = True
        except (ValueError, OSError) as exc: warnings.append({'path': str(data['poster']), 'reason': '本地海报: '+str(exc)})
    library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),work_id))
