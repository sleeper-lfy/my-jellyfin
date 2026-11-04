"""Local-only, journal-free export of portable Jellyfin/Kodi sidecars."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
import xml.etree.ElementTree as ET

from .core import check_cancelled, ImportCancelled
from .nfo import MAX_NFO

MAX_IMAGE = 20_000_000


class TargetConflict(ValueError):
    pass


def _safe(path: Path, *, directory=False):
    path = path.absolute()
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError('不向符号链接路径导出：' + str(path))
    if directory and not path.is_dir():
        raise ValueError('目录不可用：' + str(path))
    return path


def _read(path: Path, maximum):
    _safe(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError('不是普通文件：' + str(path))
        data = source.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('文件超过导出大小限制：' + str(path))
    return data


def _existing(target, overwrite, maximum=MAX_NFO):
    _safe(target)
    if not target.exists():
        return None
    if not overwrite:
        return False
    return _read(target, maximum)


def _tree(root_name, previous):
    if previous is None:
        return ET.Element(root_name)
    if re.search(br'<!\s*(DOCTYPE|ENTITY)', previous.replace(b'\x00', b''), re.I):
        raise ValueError('已有 NFO 含 DTD / 实体声明，未覆盖')
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(previous, parser=parser)
    if root.tag != root_name:
        raise ValueError('已有 NFO 类型不符，未覆盖')
    return root


def _set(root, tag, values):
    for element in list(root.findall(tag)):
        root.remove(element)
    if not isinstance(values, list):
        values = [values]
    for value in values:
        if value not in (None, ''):
            ET.SubElement(root, tag).text = str(value)


def _number(value, default=0):
    try:
        number = float(value)
        return max(0, number) if number < float('inf') else default
    except (ValueError, TypeError):
        return default


def _playback(root, file):
    _set(root, 'watched', 'true' if file.get('completed') else 'false')
    _set(root, 'playcount', 1 if file.get('completed') else 0)
    for existing in root.findall('resume'):
        root.remove(existing)
    resume = ET.SubElement(root, 'resume')
    ET.SubElement(resume, 'position').text = str(_number(file.get('position')))
    ET.SubElement(resume, 'total').text = str(_number(file.get('duration')))


def _metadata(root, work, actor_images):
    metadata = work['metadata']
    _set(root, 'title', work['title'])
    _set(root, 'year', work.get('year'))
    _set(root, 'plot', metadata.get('overview', ''))
    _set(root, 'outline', [])
    _set(root, 'genre', [])
    _set(root, 'tag', metadata.get('tags', []))
    _set(root, 'director', metadata.get('directors', []))
    _set(root, 'studio', metadata.get('studios', []))
    _set(root, 'premiered', metadata.get('released'))
    _set(root, 'releasedate', [])
    _set(root, 'mpaa', metadata.get('content_rating'))
    _set(root, 'originaltitle', metadata.get('aliases', [])[:1])
    _set(root, 'sorttitle', metadata.get('aliases', [])[1:2])
    _set(root, 'userrating', work.get('rating') or 0)
    # Ratings exported here are source ratings, never inferred from personal rating.
    rating = next((source['rating'] for source in work.get('sources', []) if source.get('rating') is not None), None)
    if rating is not None:
        _set(root, 'ratings', [])
        _set(root, 'rating', rating)
    for old in root.findall('uniqueid'):
        root.remove(old)
    for field in ('id', 'imdbid', 'imdb_id', 'tmdbid', 'tvdbid'):
        _set(root, field, [])
    for namespace, value in metadata.get('external_ids', {}).items():
        if value not in (None, ''):
            ET.SubElement(root, 'uniqueid', {'type': str(namespace)}).text = str(value)
    old_actors = {entry.findtext('name'): copy.deepcopy(entry) for entry in root.findall('actor')}
    _set(root, 'actor', [])
    for actor in metadata.get('actors', []):
        person = old_actors.get(actor['name'], ET.Element('actor'))
        _set(person, 'name', actor['name'])
        _set(person, 'role', actor.get('role', ''))
        _set(person, 'gender', actor.get('gender', 'unknown'))
        _set(person, 'alias', actor.get('aliases', []))
        if actor['name'] in actor_images:
            _set(person, 'thumb', actor_images[actor['name']])
        root.append(person)


def _show_folder(file):
    from .series import season_folder
    video = Path(file['path']).absolute()
    root = Path(file['root']).absolute()
    folder = video.parent
    # Prefer an existing show sidecar; never climb beyond the imported root.
    for parent in [folder, *folder.parents]:
        if not parent.is_relative_to(root):
            break
        if (parent / 'tvshow.nfo').is_file():
            return parent
    return folder.parent if season_folder(folder) is not None and folder.parent.is_relative_to(root) else folder


def plan_export(library, work_ids, *, overwrite=False, images=True, cancelled=None):
    """Return in-memory artifact bytes. Planning never writes files or library data."""
    result = {'entries': [], 'skipped': [], 'errors': [], 'warnings': []}
    targets = {}

    def add(target, data, previous, work_id):
        key = str(target.absolute()).casefold()
        if key in targets:
            old = targets[key]
            if old['data'] == data and (old['work_id'] == work_id or target.suffix.lower() != '.nfo'):
                return
            raise TargetConflict('多个作品的导出目标冲突：' + str(target))
        entry = {'path': str(target.absolute()), 'data': data, 'previous': previous, 'work_id': work_id}
        targets[key] = entry
        result['entries'].append(entry)

    def image(source, folder, name, work_id):
        if not source:
            return None
        path = Path(source)
        if not path.is_file():
            return None
        _safe(path)
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        from PySide6.QtGui import QImageReader
        data = _read(path, MAX_IMAGE)
        buffer = QBuffer(); buffer.setData(QByteArray(data)); buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        size = reader.size()
        format_name = bytes(reader.format()).decode('ascii').lower()
        if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > 40_000_000 or reader.read().isNull():
            raise ValueError('缓存图片无效：' + str(path))
        extension = {'jpeg': '.jpg', 'jpg': '.jpg', 'png': '.png', 'webp': '.webp'}.get(format_name)
        if not extension:
            raise ValueError('缓存图片格式不支持：' + str(path))
        # Content-based names let changed selections coexist with existing artwork.
        filename = name + '-' + hashlib.sha256(data).hexdigest()[:12] + extension
        target = folder / filename
        previous = _existing(target, overwrite, MAX_IMAGE)
        if previous is False:
            result['skipped'].append(str(target))
        elif previous != data:
            add(target, data, previous, work_id)
        return filename

    for identifier in dict.fromkeys(work_ids):
        check_cancelled(cancelled)
        start = len(result['entries'])
        try:
            work = library.work(identifier)
            # Persisted values, not movie UI's inferred gender defaults.
            work['metadata'] = json.loads(library.db.execute('SELECT metadata FROM works WHERE id=?', (identifier,)).fetchone()[0])
            identifiers_by_namespace = {}
            for record in library.db.execute('SELECT namespace,value FROM external_ids WHERE work_id=? ORDER BY namespace,value', (identifier,)):
                identifiers_by_namespace.setdefault(record['namespace'], set()).add(record['value'])
            external = dict(work['metadata'].get('external_ids', {}))
            for namespace, values in identifiers_by_namespace.items():
                if namespace in external: continue
                if len(values) == 1: external[namespace] = next(iter(values))
                else: result['warnings'].append({'work_id': identifier, 'reason': '外部编号存在多个值，未自动选择：' + namespace})
            work['metadata']['external_ids'] = external
            if work['kind'] not in {'movie', 'series', 'vr'} or not work['files']:
                result['warnings'].append({'work_id': identifier, 'reason': '仅导出有本地视频的电影、电视剧或 VR'})
                continue
            for file in work['files']:
                check_cancelled(cancelled)
                video = _safe(Path(file['path']))
                if not video.is_file():
                    raise ValueError('视频已离线或不存在：' + str(video))
                root = _safe(Path(file['root']), directory=True)
                if not video.is_relative_to(root):
                    raise ValueError('视频不在登记目录内：' + str(video))
            targets_for_work = []
            if work['kind'] == 'series':
                folders = list(dict.fromkeys(_show_folder(file) for file in work['files']))
                targets_for_work.extend((folder / 'tvshow.nfo', 'tvshow', None) for folder in folders)
                targets_for_work.extend((Path(file['path']).with_suffix('.nfo'), 'episodedetails', file) for file in work['files'])
            else:
                targets_for_work.extend((Path(file['path']).with_suffix('.nfo'), 'movie', file) for file in work['files'])
            preferred = library.setting('preferred-file:' + str(identifier))
            targets_for_work.sort(key=lambda entry: 0 if entry[2] and entry[2]['id'] == preferred else 1)
            shared_targets = set()
            for target, root_name, file in targets_for_work:
                key = str(target.absolute()).casefold()
                if key in shared_targets:
                    result['warnings'].append({'work_id': identifier, 'reason': '同名多版本共享 NFO，采用默认或首个版本的播放信息：' + str(target)})
                    continue
                shared_targets.add(key)
                check_cancelled(cancelled)
                _safe(target.parent, directory=True)
                previous = _existing(target, overwrite)
                if previous is False:
                    result['skipped'].append(str(target)); continue
                tree = _tree(root_name, previous)
                actor_images = {}
                poster = None
                fanart = None
                exported_stills = []
                if images and root_name != 'episodedetails':
                    selected = library.setting(f'artwork_{identifier}', {}).get('poster') or work.get('thumbnail')
                    try:
                        poster = image(selected, target.parent, 'lumen-poster', identifier)
                        from .artwork import still_paths
                        stills = still_paths(work)
                        fanart_source = work['metadata'].get('nfo_backdrop') or next(iter(stills), None)
                        fanart = image(fanart_source, target.parent, 'lumen-fanart', identifier)
                        for actor in work['metadata'].get('actors', []):
                            local = image(actor.get('photo_cache'), target.parent, 'lumen-actor', identifier)
                            if local: actor_images[actor['name']] = local
                        for still in stills[:40]:
                            exported = image(still, target.parent, 'lumen-still', identifier)
                            if exported: exported_stills.append(exported)
                    except (ValueError, OSError) as error:
                        result['warnings'].append({'work_id': identifier, 'reason': str(error)})
                if root_name == 'episodedetails':
                    _set(tree, 'title', file.get('title') or Path(file['path']).stem)
                    _set(tree, 'showtitle', work['title'])
                    _set(tree, 'plot', file.get('overview', ''))
                    _set(tree, 'season', file.get('season'))
                    _set(tree, 'episode', file.get('episode'))
                    _playback(tree, file)
                else:
                    _metadata(tree, work, actor_images)
                    if poster:
                        _set(tree, 'poster', poster)
                        for thumb in list(tree.findall('thumb')):
                            if thumb.get('aspect') == 'poster': tree.remove(thumb)
                        ET.SubElement(tree, 'thumb', {'aspect': 'poster'}).text = poster
                    if poster or fanart or exported_stills:
                        art = tree.find('art')
                        if art is None: art = ET.SubElement(tree, 'art')
                        if poster: _set(art, 'poster', poster)
                        if fanart or exported_stills:
                            refs = list(dict.fromkeys(([fanart] if fanart else []) + exported_stills))
                            _set(art, 'fanart', refs)
                            _set(tree, 'fanart', [])
                            fanart_node = ET.SubElement(tree, 'fanart')
                            for ref in refs: ET.SubElement(fanart_node, 'thumb').text = ref
                    if file: _playback(tree, file)
                ET.indent(tree, space='  ')
                data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
                if len(data) > MAX_NFO: raise ValueError('导出 NFO 超过 2 MB')
                add(target, data, previous, identifier)
        except ImportCancelled:
            raise
        except TargetConflict as error:
            # Ambiguous shared output belongs to neither item; don't choose a winner.
            result['entries'].clear()
            result['errors'].append({'work_id': identifier, 'reason': str(error)})
            return result
        except (ValueError, OSError, ET.ParseError) as error:
            # A malformed or conflicting work is excluded as a unit before writing.
            removed = result['entries'][start:]
            for entry in removed: targets.pop(entry['path'].casefold(), None)
            del result['entries'][start:]
            result['errors'].append({'work_id': identifier, 'reason': str(error)})
    return result


def _publish(entry, cancelled=None):
    target = Path(entry['path']); _safe(target.parent, directory=True); _safe(target)
    current = _read(target, max(MAX_NFO, MAX_IMAGE)) if target.exists() else None
    if current != entry['previous']:
        raise ValueError('目标文件在检查后发生变化，未覆盖：' + str(target))
    temporary = target.parent / ('.lumen-export-' + uuid.uuid4().hex + '.tmp')
    backup = None
    try:
        with temporary.open('xb') as output:
            for start in range(0, len(entry['data']), 1024 * 1024):
                check_cancelled(cancelled); output.write(entry['data'][start:start + 1024 * 1024])
            output.flush(); os.fsync(output.fileno())
        check_cancelled(cancelled)
        _safe(target); _safe(target.parent, directory=True)
        if entry['previous'] is not None:
            if _read(target, max(MAX_NFO, MAX_IMAGE)) != entry['previous']:
                raise ValueError('目标文件已变化，未覆盖：' + str(target))
            backup = target.with_name(target.name + '.lumen-backup-' + uuid.uuid4().hex)
            with backup.open('xb') as output:
                output.write(entry['previous']); output.flush(); os.fsync(output.fileno())
            check_cancelled(cancelled)
            if _read(target, max(MAX_NFO, MAX_IMAGE)) != entry['previous']:
                raise ValueError('目标文件已变化，原文件与备份保留')
            os.replace(temporary, target)
        elif os.name == 'nt':
            os.rename(temporary, target)
        else:
            os.link(temporary, target)
        return str(backup) if backup else None
    finally:
        temporary.unlink(missing_ok=True)


def _preflight_targets(library, identifiers):
    owners = {}
    errors = []
    for identifier in identifiers:
        try:
            work = library.work(identifier)
            if work['kind'] not in {'movie', 'series', 'vr'}: continue
            paths = [Path(file['path']).with_suffix('.nfo') for file in work['files']]
            if work['kind'] == 'series': paths += [_show_folder(file) / 'tvshow.nfo' for file in work['files']]
            for path in paths:
                key = str(path.absolute()).casefold()
                if key in owners and owners[key] != identifier:
                    errors.append({'path': str(path), 'reason': '多个作品共享 NFO 目标，未写入任何文件'})
                owners[key] = identifier
        except (ValueError, OSError) as error:
            errors.append({'work_id': identifier, 'reason': str(error)})
    return errors


def export_works(library, work_ids, *, overwrite=False, images=True, progress=None, cancelled=None):
    identifiers = list(dict.fromkeys(work_ids))
    result = {'written': 0, 'skipped': 0, 'errors': _preflight_targets(library, identifiers), 'warnings': [], 'backups': []}
    if result['errors']: return result
    # Build and release one work's bytes at a time, so a whole-library export
    # doesn't hold every poster and still in memory simultaneously.
    for work_index, identifier in enumerate(identifiers):
        check_cancelled(cancelled)
        if progress: progress(work_index, len(identifiers), '导出 NFO / 图片 · 作品 ' + str(identifier))
        plan = plan_export(library, [identifier], overwrite=overwrite, images=images, cancelled=cancelled)
        result['skipped'] += len(plan['skipped'])
        result['errors'].extend(plan['errors']); result['warnings'].extend(plan['warnings'])
        for entry in plan['entries']:
            check_cancelled(cancelled)
            try:
                backup = _publish(entry, cancelled)
                result['written'] += 1
                if backup: result['backups'].append(backup)
            except ImportCancelled:
                raise
            except (ValueError, OSError) as error:
                result['errors'].append({'path': entry['path'], 'reason': str(error)})
    return result


def preview_export(library, work_ids, *, overwrite=False, images=True, cancelled=None):
    identifiers = list(dict.fromkeys(work_ids))
    result = {'paths': [], 'skipped': [], 'errors': _preflight_targets(library, identifiers), 'warnings': []}
    if result['errors']: return result
    for identifier in identifiers:
        check_cancelled(cancelled)
        plan = plan_export(library, [identifier], overwrite=overwrite, images=images, cancelled=cancelled)
        result['paths'].extend(entry['path'] for entry in plan['entries'])
        for key in ('skipped', 'errors', 'warnings'): result[key].extend(plan[key])
    return result
