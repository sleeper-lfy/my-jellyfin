"""Folder-based series grouping and stable episode numbering for local imports."""
import hashlib
import os
from pathlib import Path
import re
import unicodedata
from . import nfo


def normalized(value):
    return unicodedata.normalize('NFKC', value)


def season_folder(folder):
    match = re.fullmatch(r'(?i)(?:season[ ._-]*|s)(\d{1,3})|第\s*(\d{1,3})\s*季', normalized(folder.name).strip())
    return int(next(value for value in match.groups() if value is not None)) if match else None


def episode_numbers(path):
    stem = normalized(Path(path).stem)
    match = re.search(r'(?i)(?:s(\d{1,3})[ ._-]*e(\d{1,5})|(\d{1,3})x(\d{1,5}))', stem)
    if match:
        return int(match.group(1) or match.group(3)), int(match.group(2) or match.group(4))
    season = season_folder(Path(path).parent)
    # Match episode markers before bare numbers: title digits, dates, resolutions
    # and release catalogue identifiers must not become episode numbers.
    match = re.search(r'第\s*(\d{1,5})\s*[巻卷話话集回]', stem)
    if not match:
        match = re.search(r'(?i)(?<![a-z])(?:ova|oad|episode|ep|e)[ ._-]*(\d{1,5})(?!\d)', stem)
    if not match:
        match = re.match(r'(?:第\s*)?(\d{1,3})(?=[ ._-]|$)', stem)
    if not match:
        match = re.search(r'[ ._-](\d{1,3})(?:[話话集回])?$', stem)
    return season if season is not None else 1, int(match.group(1)) if match else None


def folder_for(path, root, cache):
    folder = path.parent
    while folder.is_relative_to(root):
        if nfo.sibling(folder, 'tvshow.nfo', cache):
            return folder
        if folder == root:
            break
        folder = folder.parent
    return path.parent.parent if season_folder(path.parent) is not None else path.parent


def folder_key(folder):
    return 'series-folder:' + hashlib.sha256(os.path.normcase(str(folder.resolve())).encode()).hexdigest()


def natural_key(path):
    return tuple((1, int(part)) if part.isdecimal() else (0, part)
                 for part in re.split(r'(\d+)', normalized(str(path)).casefold())), str(path)


class SeriesPlan:
    def __init__(self, library, paths, root, cache, report, cancelled, partial=False, fast=False, signatures=None):
        from .core import check_cancelled
        self.groups, self.numbers, self.existing = {}, {}, {}
        self.folders = {}
        explicit, inferred = {}, []
        signatures=signatures if signatures is not None else {}
        for index, path in enumerate(paths):
            check_cancelled(cancelled)
            report(0, len(paths), f'识别电视剧目录 {index+1} / {len(paths)}', path, False)
            folder = self.folders.get(path.parent)
            if folder is None:
                folder = self.folders[path.parent] = folder_for(path, root, cache)
            if folder not in self.groups:self.groups[folder]={'folder':folder,'key':folder_key(folder),'known':None}
            group=self.groups[folder]
            row = library.db.execute('SELECT f.id,f.work_id,f.season,f.episode,w.kind FROM files f JOIN works w ON w.id=f.work_id WHERE f.path=?', (str(path),)).fetchone()
            existing = self.existing[path] = dict(row) if row else None
            if existing and existing['kind'] == 'series' and group['known'] is None:
                group['known'] = existing['work_id']
            season, episode = episode_numbers(path)
            adjacent = nfo.sibling(path.parent, path.stem + '.nfo', cache)
            unchanged=False
            if adjacent and fast and existing:
                stored=library.db.execute('SELECT size,modified,sidecars FROM import_cache WHERE file_id=?',(existing['id'],)).fetchone()
                stat=path.stat()
                unchanged=stored and stored['size']==stat.st_size and stored['modified']==stat.st_mtime_ns and stored['sidecars']==nfo.sidecar_signature(path,root,'series',cache,signatures)
            if unchanged and existing['kind']=='series':
                season,episode=existing['season'],existing['episode']
            elif adjacent:
                # Keep only two numbers in the plan, not artwork or full metadata.
                # The normal loader reports invalid NFOs as warnings below.
                try:
                    entry = nfo.read(adjacent)
                    if entry['type'] == 'episodedetails':
                        if entry['season'] is not None: season = entry['season']
                        if entry['episode'] is not None: episode = entry['episode']
                except (ValueError, OSError, nfo.ET.ParseError, ZeroDivisionError):
                    pass
            if episode is None:
                inferred.append((path, folder, season, existing))
            else:
                self.numbers[path] = (season, episode)
                explicit.setdefault((folder, season), set()).add(episode)
        included=set(paths)
        for group in self.groups.values():
            bound=library.db.execute('SELECT work_id FROM name_keys WHERE key=?',(group['key'],)).fetchone()
            if bound:group['known']=bound[0]
            if partial:
                prefix=str(group['folder'])+os.sep
                escaped=prefix.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                rows=library.db.execute("SELECT f.path,f.work_id,f.season,f.episode FROM files f JOIN works w ON w.id=f.work_id WHERE w.kind='series' AND f.path LIKE ? ESCAPE '\\' ORDER BY f.id",(escaped,))
                for row in rows:
                    path=Path(row['path'])
                    try:same=folder_for(path,root,cache)==group['folder']
                    except OSError:same=False
                    if not same:continue
                    if group['known'] is None:group['known']=row['work_id']
                    if path not in included and row['season'] is not None and row['episode'] is not None:
                        explicit.setdefault((group['folder'],row['season']),set()).add(row['episode'])
        # Keep existing inferred numbers stable when newly added files sort first.
        # Reserve old values before assigning numbers to any new unnamed episode.
        used={key:set(values) for key,values in explicit.items()}
        inferred.sort(key=lambda record:record[3] is None)
        for path, folder, season, existing in inferred:
            check_cancelled(cancelled)
            reserved=used.setdefault((folder,season),set())
            previous=existing['episode'] if existing and existing['kind']=='series' and existing['season']==season else None
            episode=previous if previous is not None and previous not in reserved else 1
            while episode in reserved:episode+=1
            self.numbers[path]=(season,episode);reserved.add(episode)

    def group(self, path):
        return self.groups[self.folders[path.parent]]
