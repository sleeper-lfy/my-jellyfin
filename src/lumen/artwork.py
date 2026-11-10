"""Shared, cache-backed still gallery for desktop and authenticated LAN clients."""
from pathlib import Path

MAX_STILLS = 40


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
    """Exact-file NFO thumbnail or video frame, with no artwork/poster fallback."""
    frame = file_thumbnail_target(library, file)
    local = work.get('metadata', {}).get('nfo_thumbnails', {})
    selected = local.get(str(file['id'])) if isinstance(local, dict) else None
    if isinstance(selected, str) and selected:
        target = _thumbnail_cache_path(library, selected)
        # Some sidecars label the same cover as both poster and thumb. Such a
        # reference is not a file preview; its real digest frame is still valid.
        posters = [work.get('thumbnail'), scraped_image_path(work, 'poster')]
        is_poster = any(isinstance(path, str) and Path(path).resolve() == target for path in posters)
        if (not is_poster or target == frame) and target.is_file() and target.stat().st_size:
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
