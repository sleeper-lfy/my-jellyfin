"""Shared, cache-backed still gallery for desktop and authenticated LAN clients."""
from pathlib import Path

MAX_STILLS = 40


def scraped_poster_path(library, work, poster=None):
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
    for path in still_paths(work):
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


def thumbnail_path(library, work):
    """Prefer explicit artwork and real stills over generated video frames."""
    selected=library.setting(f'artwork_{work["id"]}',{}).get('thumbnail')
    local=work.get('metadata',{}).get('nfo_thumbnails',{})
    files=work.get('files',[])
    paths=[selected,*still_paths(work),
           *[local.get(str(file['id'])) for file in files],
           *[library.directory/'cache'/(file['digest']+'.jpg') for file in files],
           work.get('thumbnail')]
    return next((str(path) for path in paths if path and Path(path).is_file()),None)


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
