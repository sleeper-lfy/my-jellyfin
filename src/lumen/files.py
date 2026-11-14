"""Journaled, no-overwrite file moves with verified cross-volume copies."""
import json
import os
from pathlib import Path
import re
import uuid
from .core import fingerprint, SIDECARS, check_cancelled, ImportCancelled


def related_files(source):
    """Sidecars that belong to one video: same stem in the same directory."""
    return [p for p in source.parent.iterdir() if p.is_file() and p.suffix.lower() in SIDECARS and
            (p.stem == source.stem or p.name.startswith(source.stem + '.'))]


def plan_delete(library, work_id, file_ids=None):
    """Recorded paths and cached sizes only: planning must not touch offline drives."""
    work = library.work(work_id)
    all_files=work['files']
    if file_ids is not None:
        wanted=set(file_ids)
        if not wanted or not wanted<={file['id'] for file in all_files}:raise ValueError('所选季集已改变或不属于当前作品，请重新选择')
        work={**work,'files':[file for file in all_files if file['id'] in wanted]}
    if not work['files']:
        raise ValueError('该条目没有本地视频文件')
    sizes = []
    for f in work['files']:
        cache = library.db.execute('SELECT size FROM import_cache WHERE file_id=?', (f['id'],)).fetchone()
        sizes.append(cache['size'] if cache and cache['size'] else None)
    total = sum(size for size in sizes if size is not None)
    return {'paths': [f['path'] for f in work['files']], 'known_size': all(size is not None for size in sizes), 'bytes': total}


def execute_delete(library, work_id, progress=None, cancelled=None, file_ids=None):
    """Delete every recorded video plus its sidecars, then drop the library entry.

    Any missing or undeletable file aborts with the entry intact for a retry."""
    work = library.work(work_id)
    all_files=work['files']
    if file_ids is not None:
        wanted=set(file_ids)
        if not wanted or not wanted<={file['id'] for file in all_files}:raise ValueError('所选季集已改变或不属于当前作品，请重新选择')
        work={**work,'files':[file for file in all_files if file['id'] in wanted]}
    if not work['files']:
        raise ValueError('该条目没有本地视频文件')
    marks=','.join('?' for file in work['files'])
    if library.db.execute(f'SELECT 1 FROM sessions WHERE file_id IN ({marks}) AND ended IS NULL', [file['id'] for file in work['files']]).fetchone():
        raise ValueError('请先停止该作品的播放，再删除本地文件')
    videos, missing = [], []
    sidecars = []
    for f in work['files']:
        source = Path(f['path'])
        if source.is_file():
            videos.append(source)
            try:
                sidecars.extend(related_files(source))
            except OSError as error:
                raise ValueError(f'无法读取视频所在目录：{source}（{error}）')
        else:
            missing.append(str(source))
    if missing:
        raise ValueError('以下视频当前不存在或所在磁盘离线，未执行删除；如文件已永久移除请改用“仅移出媒体库”：\n' + '\n'.join(missing))
    untouched=[Path(file['path']) for file in all_files if file['id'] not in {item['id'] for item in work['files']}]
    sidecars=[path for path in sidecars if not any(path.parent==other.parent and (path.stem==other.stem or path.name.startswith(other.stem+'.')) for other in untouched)]
    targets = list(dict.fromkeys([*sidecars, *videos]))
    total = len(targets)
    errors = []
    for index, target in enumerate(targets):
        check_cancelled(cancelled)
        if progress:
            progress(index, total, target.name)
        try:
            target.unlink()
        except OSError as error:
            errors.append(f'{target}：{error}')
    if progress:
        progress(total, total, '删除完成')
    if errors:
        raise ValueError('以下文件未能删除，条目已保留，可重试或改用“仅移出媒体库”：\n' + '\n'.join(errors))
    if file_ids is None:
        library.remove_catalog(work_id)
        return {'deleted':total}
    result=library.remove_local_records(work_id,file_ids)
    return {'deleted':total,**result}


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:150] or 'Untitled'
    if value.upper().split('.')[0] in {'CON','PRN','AUX','NUL', *[f'COM{i}' for i in range(1,10)], *[f'LPT{i}' for i in range(1,10)]}:
        value = '_' + value
    return value


def plan_move(library, work_id, destination, rule=None, cancelled=None, media_library_id=None, file_ids=None):
    """Build a read-only, fully checked move plan; execution revalidates its hashes."""
    from .organize_templates import load_rule, validate_rule, destinations, companion_copies
    def hash_file(path):return fingerprint(path,cancelled=cancelled) if cancelled else fingerprint(path)
    check_cancelled(cancelled)
    work = library.work(work_id,media_library_id) if media_library_id is not None else library.work(work_id)
    if file_ids is not None:work={**work,'files':[f for f in work['files'] if f['id'] in file_ids]}
    if not work['files']:raise ValueError('没有属于当前整理范围的文件')
    root = Path(destination).resolve()
    selected = load_rule(library, work['kind'], root) if rule is None else validate_rule(rule)
    pairs = []
    items = destinations(work, root, selected)
    for item in items:
        check_cancelled(cancelled)
        f, folder, stem = item['file'], item['folder'], item['stem']
        source = Path(f['path'])
        if source.is_symlink():
            raise ValueError('不整理符号链接视频：' + str(source))
        related = related_files(source)
        for p in [source, *related]:
            if p.is_symlink():
                raise ValueError('不整理符号链接附属文件：' + str(p))
            # Keep language/forced subtitles and other same-stem sidecar suffixes intact.
            suffix = p.name[len(source.stem):]
            target = folder / (stem + suffix)
            if not target.resolve().is_relative_to(root):
                raise ValueError('目标目录包含指向分区外部的符号链接')
            if p.resolve() == target.resolve():
                continue
            if target.exists():
                raise FileExistsError(f'目标已存在：{target}')
            pairs.append({'source': str(p), 'target': str(target), 'digest': hash_file(p), 'file_id': f['id'] if p == source else None,
                          'root': str(root), 'state': 'pending'})
    copies = companion_copies(work, items, pairs, root)
    shared = {str(source) for source, target in copies}
    for pair in pairs:
        if pair['source'] in shared:
            pair['keep_source'] = True
    for source, target in copies:
        if not target.resolve().is_relative_to(root):
            raise ValueError('NFO 配套图片目标越过整理根目录')
        if source.resolve() == target.resolve():
            continue
        digest = hash_file(source)
        if target.exists():
            if not target.is_symlink() and target.is_file() and hash_file(target) == digest:
                continue
            raise FileExistsError('配套资料目标已存在：' + str(target))
        pairs.append({'source':str(source),'target':str(target),'digest':digest,'file_id':None,
                      'root':str(root),'state':'pending','keep_source':True})
    # Shared assets may be copied to multiple seasons; moving a source twice is forbidden.
    sources = {}; unique = {}
    for pair in pairs:
        previous = sources.get(pair['source'])
        if previous and previous['target'] != pair['target'] and not (previous.get('keep_source') and pair.get('keep_source')):
            raise FileExistsError('附属文件对应多个目标，请先确认：' + pair['source'])
        sources[pair['source']] = pair
        unique[(pair['source'],pair['target'])] = pair
    pairs = list(unique.values())
    targets = [p['target'].casefold() for p in pairs]
    if len(set(targets)) != len(targets):
        raise FileExistsError('整理后出现同名冲突')
    return pairs


def execute_move(library, pairs=None, task_id=None, cancelled=None):
    def hash_file(path):return fingerprint(path,cancelled=cancelled) if cancelled else fingerprint(path)
    task_id = task_id or uuid.uuid4().hex
    if pairs is None:
        row = library.db.execute('SELECT payload FROM tasks WHERE id=? AND kind="move"', (task_id,)).fetchone()
        if not row:
            raise ValueError('整理任务不存在')
        pairs = json.loads(row[0])
    def save(status, error=None):
        library.task(task_id, 'move', status, pairs, {'completed': sum(p['state'] == 'done' for p in pairs), 'total': len(pairs)}, error)
    save('running')
    try:
        for p in pairs:
            check_cancelled(cancelled)
            if p['state'] == 'done':
                continue
            source, target = Path(p['source']), Path(p['target'])
            target.parent.mkdir(parents=True, exist_ok=True)
            if p['state'] in {'pending', 'copying'}:
                if not source.is_file() or hash_file(source) != p['digest']:
                    raise ValueError(f'源文件已改变：{source}')
                if p['state'] == 'pending':
                    if target.exists():
                        raise FileExistsError(f'目标已存在：{target}')
                    p['temporary'] = str(target.parent / ('.lumen-' + uuid.uuid4().hex + '.partial'))
                    p['state'] = 'copying'
                    save('running')
                temporary = Path(p['temporary'])
                # Only the uniquely journaled temporary file belongs to this task.
                with source.open('rb') as incoming, temporary.open('wb') as outgoing:
                    for block in iter(lambda: incoming.read(4 * 1024 * 1024), b''):
                        check_cancelled(cancelled)
                        outgoing.write(block)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                if hash_file(temporary) != p['digest'] or hash_file(source) != p['digest']:
                    raise IOError('复制校验失败，原文件保留')
                p['state'] = 'verified'
                save('running')
            if p['state'] == 'verified':
                temporary = Path(p['temporary'])
                # Hard-link publication is atomic and refuses to overwrite existing files.
                # Both files are in the same destination directory / filesystem.
                if temporary.exists():
                    if target.exists():
                        if not os.path.samefile(temporary, target):
                            raise FileExistsError(f'目标已存在：{target}')
                    else:
                        if os.name == 'nt':
                            os.rename(temporary, target)  # Windows rename refuses overwrite, including on exFAT.
                        else:
                            os.link(temporary, target)
                    p['state'] = 'published'
                    save('running')
                    if temporary.exists():
                        temporary.unlink()
                elif os.name == 'nt' and target.is_file() and hash_file(target) == p['digest']:
                    # Recover a crash immediately after the atomic Windows rename.
                    p['state'] = 'published'
                    save('running')
                else:
                    raise IOError('校验后的临时文件丢失；保留原文件，需人工检查')
            if p['state'] == 'published':
                if not target.is_file() or hash_file(target) != p['digest']:
                    raise IOError('目标文件校验失败，原文件保留')
                temporary = Path(p.get('temporary', ''))
                if temporary.is_file() and os.path.samefile(temporary, target):
                    temporary.unlink()
                if source.exists() and not p.get('keep_source',False):
                    if hash_file(source) != p['digest']:
                        raise IOError('源文件在整理期间发生改变，保留两份文件')
                    source.unlink()
                if p['file_id']:
                    with library.db:
                        library.db.execute('UPDATE files SET path=?,root=? WHERE id=?', (str(target), p['root'], p['file_id']))
                p['state'] = 'done'
                save('running')
        save('done')
    except ImportCancelled:
        save('cancelled','整理已停止，原文件保留，可恢复任务');raise
    except Exception as exc:
        save('failed', str(exc))
        raise
    return task_id
