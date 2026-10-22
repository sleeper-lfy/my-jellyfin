"""Journaled, no-overwrite file moves with verified cross-volume copies."""
import json
import os
from pathlib import Path
import re
import uuid
from .core import fingerprint, SIDECARS


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:150] or 'Untitled'
    if value.upper().split('.')[0] in {'CON','PRN','AUX','NUL', *[f'COM{i}' for i in range(1,10)], *[f'LPT{i}' for i in range(1,10)]}:
        value = '_' + value
    return value


def plan_move(library, work_id, destination):
    work = library.work(work_id)
    root = Path(destination).resolve()
    pairs = []
    for f in work['files']:
        source = Path(f['path'])
        folder = root / safe_name(work['title'] + (f" ({work['year']})" if work['year'] else ''))
        if work['kind'] == 'series':
            folder /= f"Season {f['season']:02}"
        if work['kind'] == 'other':
            folder = root / Path(f['root']).name / source.relative_to(f['root']).parent
        related = [p for p in source.parent.iterdir() if p.is_file() and p.suffix.lower() in SIDECARS and
                   (p.stem == source.stem or p.name.startswith(source.stem + '.'))]
        for p in [source, *related]:
            target = folder / p.name
            if not target.resolve().is_relative_to(root):
                raise ValueError('目标目录包含指向分区外部的符号链接')
            if p.resolve() == target.resolve():
                continue
            if target.exists():
                raise FileExistsError(f'目标已存在：{target}')
            pairs.append({'source': str(p), 'target': str(target), 'digest': fingerprint(p), 'file_id': f['id'] if p == source else None,
                          'root': str(root), 'state': 'pending'})
    # A shared subtitle may be associated with only one operation.
    pairs = list({p['source']: p for p in pairs}.values())
    targets = [p['target'].casefold() for p in pairs]
    if len(set(targets)) != len(targets):
        raise FileExistsError('整理后出现同名冲突')
    return pairs


def execute_move(library, pairs=None, task_id=None):
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
            if p['state'] == 'done':
                continue
            source, target = Path(p['source']), Path(p['target'])
            target.parent.mkdir(parents=True, exist_ok=True)
            if p['state'] in {'pending', 'copying'}:
                if not source.is_file() or fingerprint(source) != p['digest']:
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
                        outgoing.write(block)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                if fingerprint(temporary) != p['digest'] or fingerprint(source) != p['digest']:
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
                elif os.name == 'nt' and target.is_file() and fingerprint(target) == p['digest']:
                    # Recover a crash immediately after the atomic Windows rename.
                    p['state'] = 'published'
                    save('running')
                else:
                    raise IOError('校验后的临时文件丢失；保留原文件，需人工检查')
            if p['state'] == 'published':
                if not target.is_file() or fingerprint(target) != p['digest']:
                    raise IOError('目标文件校验失败，原文件保留')
                temporary = Path(p.get('temporary', ''))
                if temporary.is_file() and os.path.samefile(temporary, target):
                    temporary.unlink()
                if source.exists():
                    if fingerprint(source) != p['digest']:
                        raise IOError('源文件在整理期间发生改变，保留两份文件')
                    source.unlink()
                if p['file_id']:
                    with library.db:
                        library.db.execute('UPDATE files SET path=?,root=? WHERE id=?', (str(target), p['root'], p['file_id']))
                p['state'] = 'done'
                save('running')
        save('done')
    except Exception as exc:
        save('failed', str(exc))
        raise
    return task_id
