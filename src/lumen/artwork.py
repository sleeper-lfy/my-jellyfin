"""Shared, cache-backed still gallery for desktop and authenticated LAN clients."""
from pathlib import Path

MAX_STILLS = 40


def still_paths(work):
    metadata=work['metadata']
    paths=[*[path for group in metadata.get('episode_stills',{}).values() for path in group], *metadata.get('nfo_stills',[]), *[entry['path'] for entry in metadata.get('stills_cache',[]) if isinstance(entry,dict) and entry.get('url') in metadata.get('stills',[]) and entry.get('path')]]
    return list(dict.fromkeys(paths))[:MAX_STILLS]
