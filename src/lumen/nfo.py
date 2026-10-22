"""Read local Jellyfin/Kodi sidecars without network access or modifying originals."""
from pathlib import Path
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET

MAX_NFO = 2_000_000


def sibling(folder, name, cache=None):
    if cache is None:
        return next((p for p in folder.iterdir() if p.name.casefold() == name.casefold() and p.is_file() and not p.is_symlink()), None)
    if folder not in cache:
        cache[folder] = {p.name.casefold():p for p in folder.iterdir() if p.is_file() and not p.is_symlink()}
    return cache[folder].get(name.casefold())


def sidecar_signature(video, root, kind, cache, signatures):
    folders = [video.parent]
    if kind == 'series':
        folders.extend(p for p in video.parent.parents if p.is_relative_to(root))
    for folder in folders:
        if folder not in signatures:
            sibling(folder, '', cache)
            records = []
            for path in cache[folder].values():
                if path.suffix.lower() in {'.nfo','.jpg','.jpeg','.png'}:
                    stat = path.stat()
                    records.append((path.name,stat.st_size,stat.st_mtime_ns))
            extra=folder/'extrafanart'
            if extra.is_dir() and not extra.is_symlink():
                for image in extra.iterdir():
                    if image.is_file() and not image.is_symlink() and image.suffix.lower() in {'.jpg','.jpeg','.png'}:
                        stat=image.stat();records.append(('extrafanart/'+image.name,stat.st_size,stat.st_mtime_ns))
            signatures[folder] = hashlib.sha256(repr(sorted(records)).encode()).hexdigest()
    return hashlib.sha256(''.join(signatures[p] for p in folders).encode()).hexdigest()


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
            'season': integer('season',0,999) if tree.tag == 'episodedetails' and text('season') != '-1' else None,
            'episode': integer('episode',0,99999) if tree.tag == 'episodedetails' and text('episode') != '-1' else None,
            'showtitle': text('showtitle'), 'rating': rating, 'userrating': integer('userrating',0,10),
            'completed': text('watched').lower() == 'true' or (integer('playcount',0,1000000) or 0) > 0,
            'position': position, 'thumbs': values('art/poster') + values('poster') + [(e.text or '').strip() for e in tree.findall('thumb') if e.get('aspect') == 'poster'],
            'thumbnail_refs': values('art/thumb') + [(e.text or '').strip() for e in tree.findall('thumb') if e.get('aspect') != 'poster'],
            'still_refs': values('art/fanart') + values('fanart') + (values('thumb') + values('art/thumb') if tree.tag=='episodedetails' else []), 'path': path}


def load(video, root, kind, warnings, cache=None):
    """Invalid sidecars are warnings; filename import remains available."""
    def safe(path):
        if not path: return None
        try: return read(path)
        except (ValueError, OSError, ET.ParseError, ZeroDivisionError) as exc:
            warnings.append({'path': str(path), 'reason': 'NFO: ' + str(exc)})
            return None
    adjacent = sibling(video.parent, video.stem + '.nfo', cache)
    show = None
    if kind == 'series':
        folder = video.parent
        while folder.is_relative_to(root):
            candidate = sibling(folder, 'tvshow.nfo', cache)
            if candidate:
                show = safe(candidate)
                break
            if folder == root: break
            folder = folder.parent
    elif not adjacent:
        from .core import VIDEO_EXTENSIONS
        count_key = (video.parent, 'video_count')
        if cache is not None:
            if count_key not in cache:
                cache[count_key] = sum(p.suffix.lower() in VIDEO_EXTENSIONS for p in cache[video.parent].values())
            count = cache[count_key]
        else:
            count = sum(p.suffix.lower() in VIDEO_EXTENSIONS for p in video.parent.iterdir() if p.is_file())
        if count == 1:
            adjacent = sibling(video.parent, 'movie.nfo', cache)
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
    return {'work': work, 'entry': entry, 'poster': poster(video, root, work, kind, warnings, cache),
            'thumbnail': local_thumbnail(video,root,entry,cache),
            'backdrop': backdrop(video, root, work, cache), 'stills': stills(video,root,work,cache),
            'episode_stills': stills(video,root,entry,cache,scan_extra=not work or entry and entry['path'].parent!=work['path'].parent) if kind=='series' and entry else []}


def stills(video, root, work, cache=None, scan_extra=True):
    folder=work['path'].parent if work else video.parent
    candidates=[]
    for value in (work or {}).get('still_refs',[]):
        if re.match(r'^https?://',value,re.I):
            continue
        # Old Jellyfin absolute paths may point at another drive. Relocate the
        # sidecar by its name, including the conventional extrafanart folder.
        normalized=value.replace('\\','/')
        local=Path(normalized)
        candidates.extend([folder/local.name, folder/'extrafanart'/local.name])
        if not re.match(r'^[a-z]:',normalized,re.I) and not local.is_absolute():
            candidates.append(folder/local)
    extra=folder/'extrafanart'
    if scan_extra and extra.is_dir() and not extra.is_symlink():
        candidates.extend(sorted(extra.iterdir()))
    result=[]
    for path in candidates:
        if path.suffix.lower() in {'.jpg','.jpeg','.png'} and path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
            resolved=path.resolve()
            if resolved not in result:result.append(resolved)
            if len(result)>=40:break
    return result


def backdrop(video, root, work, cache=None):
    folder = work['path'].parent if work else video.parent
    for value in (work or {}).get('still_refs',[]):
        candidate=local_reference(folder,value,root,cache)
        if candidate:return candidate
    for name in [video.stem + '-fanart.jpg', video.stem + '-fanart.png', 'fanart.jpg', 'fanart.png', 'backdrop.jpg', 'backdrop.png']:
        candidate = sibling(folder, name, cache)
        if candidate and candidate.resolve().is_relative_to(root):
            return candidate
    return None


def poster(video, root, work, kind, warnings, cache=None):
    folder = work['path'].parent if work else video.parent
    candidates = []
    for value in (work or {}).get('thumbs', []):
        if value and not re.match(r'^https?://', value, re.I):
            relative=Path(value.replace('\\','/'))
            candidate=sibling(folder,relative.name,cache)
            if candidate:candidates.append(candidate)
            if not relative.is_absolute() and not re.match(r'^[a-z]:',value,re.I):candidates.append(folder/relative)
    for name in [video.stem+'-poster.jpg', video.stem+'-poster.png', 'poster.jpg','poster.png','folder.jpg','folder.png']:
        candidate = sibling(folder, name, cache)
        if candidate: candidates.append(candidate)
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink() and candidate.resolve().is_relative_to(root): return candidate
    return None


def local_reference(folder,value,root,cache=None):
    if not value or re.match(r'^https?://',value,re.I):return None
    normalized=value.replace('\\','/')
    relative=Path(normalized)
    candidates=[sibling(folder,relative.name,cache),folder/'extrafanart'/relative.name]
    if not relative.is_absolute() and not re.match(r'^[a-z]:',normalized,re.I):candidates.insert(0,folder/relative)
    elif relative.is_absolute():candidates.insert(0,relative)
    return next((path for path in candidates if path and path.is_file() and not path.is_symlink()
                 and path.resolve().is_relative_to(root)),None)


def local_thumbnail(video,root,entry,cache=None):
    folder=entry['path'].parent if entry else video.parent
    values=(entry or {}).get('thumbnail_refs',[])+[video.stem+'-thumb.jpg',video.stem+'-thumb.png','thumb.jpg','thumb.png','landscape.jpg']
    return next((path for value in values if (path:=local_reference(folder,value,root,cache))),None)


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
        position = min(entry['position'] or 0, duration) if duration > 0 else (entry['position'] or 0)
        library.db.execute('UPDATE files SET position=?,completed=? WHERE id=?',(0 if entry['completed'] else position,int(entry['completed']),file_id))
    if data['poster'] and 'poster' not in item['locked']:
        try:
            cover = cache_poster(data['poster'],library.directory)
            library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(cover,work_id))
            metadata['nfo_poster'] = True
        except (ValueError, OSError) as exc: warnings.append({'path': str(data['poster']), 'reason': '本地海报: '+str(exc)})
    if data.get('thumbnail') and 'thumbnail' not in item['locked']:
        try:metadata.setdefault('nfo_thumbnails',{})[str(file_id)]=cache_poster(data['thumbnail'],library.directory)
        except (ValueError,OSError) as exc:warnings.append({'path':str(data['thumbnail']),'reason':'本地缩略图: '+str(exc)})
    if data.get('backdrop'):
        try:
            metadata['nfo_backdrop'] = cache_poster(data['backdrop'], library.directory)
        except (ValueError, OSError) as exc:
            warnings.append({'path': str(data['backdrop']), 'reason': '本地背景图: ' + str(exc)})
    if data.get('episode_stills') and 'stills' not in item['locked']:
        cached=[]
        for image in data['episode_stills']:
            try:cached.append(cache_poster(image,library.directory))
            except (ValueError,OSError) as exc:warnings.append({'path':str(image),'reason':'单集剧照: '+str(exc)})
        metadata.setdefault('episode_stills',{})[str(file_id)]=list(dict.fromkeys(cached))
    if data.get('stills') and 'stills' not in item['locked']:
        cached=[]
        for image in data['stills']:
            try:cached.append(cache_poster(image,library.directory))
            except (ValueError,OSError) as exc:warnings.append({'path':str(image),'reason':'本地剧照: '+str(exc)})
        metadata['nfo_stills']=list(dict.fromkeys(cached))
    library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),work_id))
