"""Shared, cache-backed still gallery for desktop and authenticated LAN clients."""
from pathlib import Path

MAX_STILLS = 40


def still_paths(work):
    metadata=work['metadata']
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
