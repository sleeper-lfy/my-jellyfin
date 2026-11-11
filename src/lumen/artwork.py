"""Shared, cache-backed still gallery for desktop and authenticated LAN clients."""
from pathlib import Path
from functools import lru_cache

MAX_STILLS = 40


class PosterPathError(ValueError):
    pass


@lru_cache(maxsize=256)
def _poster_dimensions(path, modified, size):
    """Read cached image headers, not pixels; invalidate after any file change."""
    from .image_isolation import should_isolate, run_image_operation
    if should_isolate():
        return run_image_operation('dimensions',path=str(Path(path).absolute()),modified=modified,size=size)
    from PySide6.QtGui import QImageReader
    bounds = QImageReader(path).size()
    return bounds.width(), bounds.height()


def poster_path(library, work, *, probe=True, cache_only=True):
    """Choose poster artwork, never the work's known video/thumbnail fallback.

    Listings use probe=False and perform only role/path checks. GET and desktop
    rendering additionally validate image headers; untyped legacy images must
    have the existing portrait-poster proportions.
    """
    import re
    metadata = work.get('metadata', {})
    selected = library.setting(f'artwork_{work["id"]}', {})
    if not isinstance(selected, dict):selected = {}
    cache = library.directory / 'cache'
    frames = {(cache / (file['digest'] + '.jpg')).resolve() for file in work.get('files', [])
              if isinstance(file.get('digest'), str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', file['digest'])}
    local = metadata.get('nfo_thumbnails', {})
    thumbs = [selected.get('thumbnail'), scraped_image_path(work, 'cover')]
    if isinstance(local, dict):thumbs.extend(local.values())
    thumbnail_paths = {Path(path).resolve() for path in thumbs if isinstance(path, str) and path}

    def candidate(path, role):
        if not isinstance(path, (str, Path)) or not path:return None
        source = Path(path)
        if source.is_symlink():raise PosterPathError('海报路径无效')
        try:target = _thumbnail_cache_path(library, source) if cache_only else source.resolve()
        except ValueError:raise PosterPathError('海报路径无效') from None
        if target in frames or role == 'legacy' and target in thumbnail_paths:return None
        try:
            if not target.is_file() or not (stat := target.stat()).st_size:return None
            if probe:
                width, height = _poster_dimensions(str(target), stat.st_mtime_ns, stat.st_size)
                if width <= 0 or height <= 0 or width * height > 40_000_000:return None
                if role == 'legacy' and not .55 <= width / height <= .8:return None
            return str(target)
        except OSError:
            return None

    manual = candidate(selected.get('poster'), 'manual')
    if manual:return manual
    sources = [scraped_image_path(work, 'poster')]
    poster_url = metadata.get('poster')
    if isinstance(poster_url, str) and poster_url:
        import hashlib
        # Older plugin/preview caches predate the explicit poster_cache role.
        sources.append(cache / (hashlib.sha256(poster_url.encode()).hexdigest() + '.jpg'))
        sources.extend(cache / ('match-' + hashlib.sha256((source['plugin'] + poster_url).encode()).hexdigest() + '.jpg') for source in work.get('sources', []))
    legacy = work.get('thumbnail')
    source_legacy = legacy and any(path and Path(path).resolve() == Path(legacy).resolve() for path in sources)
    role = 'nfo' if metadata.get('nfo_poster') else 'source' if source_legacy else 'legacy'
    if 'poster' in work.get('locked', []):return candidate(legacy, role)
    if metadata.get('nfo_poster'):
        current = candidate(legacy, 'nfo')
        if current:return current
    for source in sources:
        current = candidate(source, 'source')
        if current:return current
    # A stale source cache must not re-enter through the legacy column.
    entry = metadata.get('poster_cache', {})
    if isinstance(entry, dict) and entry.get('path') and entry.get('url') != metadata.get('poster') and legacy and Path(entry['path']).resolve() == Path(legacy).resolve():return None
    return candidate(legacy, role)


def scraped_poster_path(library, work, poster=None, *, fallback_paths=()):
    """Select a portrait still or crop a copy when the scraped cover is unsuitable."""
    from PySide6.QtCore import QSize, QSaveFile, QIODevice
    from .images import decode
    from .artwork_ui import crop_image
    import hashlib

    def read(path):
        return decode(str(path),QSize(4096,4096)) if path and Path(path).is_file() else None

    def suitable(image):
        return image is not None and not image.isNull() and .55 <= image.width()/image.height() <= .8

    picture=read(poster)
    if suitable(picture):return str(poster)
    first=None
    for path in [*still_paths(work), *fallback_paths]:
        image=read(path)
        if image is None or image.isNull():continue
        if suitable(image):return str(path)
        if first is None:first=(path,image)
    if first is None:return str(poster) if poster else None
    path,image=first
    source=Path(path);revision=hashlib.sha256((str(source)+str(source.stat().st_mtime_ns)+str(source.stat().st_size)).encode()).hexdigest()
    target=library.directory/'cache'/('poster-still-'+revision+'.jpg')
    output=QSaveFile(str(target))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly) or not crop_image(image,'poster','center').save(output,'JPEG',95) or not output.commit():
        raise ValueError('剧照海报保存失败，原封面保留')
    return str(target)


def scraped_image_path(work, role):
    """Use only host-cached artwork belonging to the current source URL."""
    metadata=work.get('metadata',{})
    entry=metadata.get(role+'_cache',{})
    if not isinstance(entry,dict) or entry.get('url')!=metadata.get(role):return None
    path=entry.get('path')
    return str(path) if path and Path(path).is_file() else None


def thumbnail_path(library, work):
    """Prefer explicit artwork and real stills over generated video frames."""
    selected=library.setting(f'artwork_{work["id"]}',{}).get('thumbnail')
    local=work.get('metadata',{}).get('nfo_thumbnails',{})
    files=work.get('files',[])
    paths=[selected,scraped_image_path(work,'cover'),*still_paths(work),
           *[local.get(str(file['id'])) for file in files],
           *[library.directory/'cache'/(file['digest']+'.jpg') for file in files],
           scraped_image_path(work,'poster'),work.get('thumbnail')]
    return next((str(path) for path in paths if path and Path(path).is_file()),None)


def file_thumbnail_target(library, file):
    """A frame cache belongs to one file; a database digest is never a path."""
    import re
    digest = file.get('digest')
    if not isinstance(digest, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', digest):
        raise ValueError('无效缩略图缓存编号')
    return _thumbnail_cache_path(library, library.directory / 'cache' / (digest + '.jpg'))


def _thumbnail_cache_path(library, path):
    candidate = Path(path)
    target = candidate.resolve()
    if candidate.is_symlink() or not target.is_relative_to((library.directory / 'cache').resolve()):
        raise ValueError('缩略图路径不在缓存内')
    return target


def file_thumbnail_path(library, work, file):
    """Reuse explicit thumbnail roles while keeping multi-episode previews file-specific."""
    frame = file_thumbnail_target(library, file)
    metadata = work.get('metadata', {})
    artwork = library.setting(f'artwork_{work["id"]}', {})
    if not isinstance(artwork, dict):artwork = {}
    posters = [artwork.get('poster'), scraped_image_path(work, 'poster')]
    if metadata.get('nfo_poster'):
        posters.append(work.get('thumbnail'))

    def known_poster(target):
        return any(isinstance(path, str) and Path(path).resolve() == target for path in posters)

    # Movies can share artwork between alternate files. Other multi-file works
    # (series, creators, folders) must not show another episode's thumbnail.
    shared = work.get('kind') == 'movie' or len(work.get('files', [])) == 1
    if shared:
        manual = artwork.get('thumbnail')
        if isinstance(manual, str) and manual:
            target = _thumbnail_cache_path(library, manual)
            if target.is_file() and target.stat().st_size:return target
        cover = scraped_image_path(work, 'cover')
        if cover:
            target = _thumbnail_cache_path(library, cover)
            same_source = bool(metadata.get('poster')) and metadata.get('cover') == metadata.get('poster')
            if not same_source and not known_poster(target) and target.stat().st_size:return target
        for path in still_paths(work):
            target = _thumbnail_cache_path(library, path)
            if not known_poster(target) and target.is_file() and target.stat().st_size:return target

    local = metadata.get('nfo_thumbnails', {})
    selected = local.get(str(file['id'])) if isinstance(local, dict) else None
    if isinstance(selected, str) and selected:
        target = _thumbnail_cache_path(library, selected)
        # The historical works.thumbnail column also stores frames/NFO thumbs;
        # only an explicit poster role can identify it as a poster.
        if (not known_poster(target) or target == frame) and target.is_file() and target.stat().st_size:
            return target
    return frame if frame.is_file() and frame.stat().st_size else None


def capture_file_thumbnail(library, file, cancelled=None):
    """Create a frame atomically; callers bound concurrent decoding separately."""
    import os
    import tempfile
    from .core import thumbnail, check_cancelled
    source = Path(file['path']).resolve()
    if not source.is_relative_to(Path(file['root']).resolve()) or not source.is_file():
        raise ValueError('视频离线或不在媒体目录内')
    target = file_thumbnail_target(library, file)
    check_cancelled(cancelled)
    with tempfile.NamedTemporaryFile(prefix='frame-', suffix='.jpg', dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        thumbnail(source, temporary, file.get('duration') or 0, cancelled=cancelled)
        check_cancelled(cancelled)
        if not temporary.is_file() or not temporary.stat().st_size:
            raise ValueError('未能生成视频缩略图')
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def still_paths(work):
    metadata=work.get('metadata',{})
    paths=[*[path for group in metadata.get('episode_stills',{}).values() for path in group], *metadata.get('nfo_stills',[]), *[entry['path'] for entry in metadata.get('stills_cache',[]) if isinstance(entry,dict) and entry.get('url') in metadata.get('stills',[]) and entry.get('path')]]
    return list(dict.fromkeys(paths))[:MAX_STILLS]


def detail_sources(library,work_id):
    from .plugins import Plugins
    work=library.work(work_id)
    plugins={plugin['id']:plugin for plugin in Plugins(library).installed()
             if plugin['config'].get('enabled') and 'detail' in plugin['capabilities']}
    return [source for source in work['sources'] if source['plugin'] in plugins]


def refresh_details(library,work_id,progress=None):
    """Resolve brief discovery records by their exact source ID before caching resources."""
    from .plugins import Plugins
    manager=Plugins(library)
    sources=detail_sources(library,work_id)
    errors=[]
    for index,source in enumerate(sources):
        try:
            records=manager.run(source['plugin'],'detail',url=source['url'])
            exact=[record for record in records if str(record['id'])==str(source['source_id'])]
            if len(exact)!=1:
                raise ValueError('详情来源标识不匹配，未更新资料')
            manager.merge(source['plugin'],exact[0],work_id)
        except Exception as error:
            errors.append(source['site']+': '+str(error))
        if progress:progress(index+1,len(sources),source['site'])
    return {'sources':len(sources),'errors':errors}
