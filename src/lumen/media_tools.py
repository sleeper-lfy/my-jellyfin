"""Per-file playback data, bookmarks, directory monitoring and read-only audits."""
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
from .core import VIDEO_EXTENSIONS, check_cancelled, now


def media_file(library, file_id):
    row = library.db.execute('SELECT * FROM files WHERE id=?', (file_id,)).fetchone()
    if not row: raise ValueError('视频不存在')
    return dict(row)


def preferences(library, file_id, changes=None):
    media_file(library, file_id)
    row = library.db.execute('SELECT value FROM playback_preferences WHERE file_id=?', (file_id,)).fetchone()
    value = json.loads(row[0]) if row else {}
    if changes is not None:
        if not isinstance(changes, dict) or not changes.keys() <= {'subtitle_delay','subtitle_size','subtitle_position','vr'}:
            raise ValueError('无效播放设置')
        for key in ('subtitle_delay','subtitle_size','subtitle_position'):
            if key not in changes: continue
            number = changes[key]
            low, high = {'subtitle_delay':(-600,600),'subtitle_size':(12,64),'subtitle_position':(5,95)}[key]
            if type(number) not in (int,float) or not math.isfinite(number) or not low <= number <= high:
                raise ValueError('字幕参数超出范围')
        if 'vr' in changes:
            vr = changes['vr']
            if not isinstance(vr,dict) or not vr.keys() <= {'fish','headset','swap','tracking','swipe_seek','fov','yaw','pitch'}:
                raise ValueError('无效 VR 参数')
            for key,number in vr.items():
                if key in {'fov','yaw','pitch'}:
                    low, high = {'fov':(50,110),'yaw':(-180,180),'pitch':(-85,85)}[key]
                    if type(number) not in (int,float) or not math.isfinite(number) or not low <= number <= high: raise ValueError('VR 参数超出范围')
                elif type(number) is not bool: raise ValueError('VR 开关须为布尔值')
            changes = {**changes, 'vr':{**value.get('vr',{}),**vr}}
        value.update(changes)
        with library.db:
            library.db.execute('INSERT OR REPLACE INTO playback_preferences VALUES (?,?)', (file_id,json.dumps(value)))
    return value


def bookmarks(library, file_id):
    media_file(library,file_id)
    return [dict(row) for row in library.db.execute('SELECT * FROM bookmarks WHERE file_id=? ORDER BY position,created',(file_id,))]


def add_bookmark(library,file_id,position,title='',note=''):
    file = media_file(library,file_id)
    if type(position) not in (int,float) or not math.isfinite(position) or position < 0 or position > (file['duration'] or 864000):
        raise ValueError('书签时间超出范围')
    if not isinstance(title,str) or not isinstance(note,str) or len(title)>120 or len(note)>2000: raise ValueError('书签文字过长')
    if library.db.execute('SELECT COUNT(*) FROM bookmarks WHERE file_id=?',(file_id,)).fetchone()[0]>=500:raise ValueError('每个视频最多保存 500 个书签')
    item = {'id':uuid.uuid4().hex,'file_id':file_id,'position':position,'title':title.strip() or f'{int(position)//60:02}:{int(position)%60:02}',
            'note':note.strip(),'image':None,'created':now()}
    with library.db:
        library.db.execute('INSERT INTO bookmarks VALUES (:id,:file_id,:position,:title,:note,:image,:created)',item)
    return item


def capture_bookmark(library,bookmark_id,cancelled=None):
    from .core import thumbnail
    row = library.db.execute('SELECT b.*,f.path,f.root,f.duration FROM bookmarks b JOIN files f ON f.id=b.file_id WHERE b.id=?',(bookmark_id,)).fetchone()
    if not row: raise ValueError('书签不存在')
    path = Path(row['path']).resolve()
    if not path.is_relative_to(Path(row['root']).resolve()) or not path.is_file(): raise ValueError('视频离线或已移动')
    target = library.directory/'cache'/('bookmark-'+bookmark_id+'.jpg')
    second=min(row['position'],max(0,row['duration']-.1)) if row['duration']>0 else row['position']
    thumbnail(path,target,row['duration'],at=second,cancelled=cancelled)
    if not target.is_file() or not target.stat().st_size:raise ValueError('未能生成该时间点截图')
    with library.db: library.db.execute('UPDATE bookmarks SET image=? WHERE id=?',(str(target),bookmark_id))
    return str(target)


def delete_bookmark(library,bookmark_id):
    with library.db: library.db.execute('DELETE FROM bookmarks WHERE id=?',(bookmark_id,))


def watch_folders(library,progress=None,clock=time.time,cancelled=None):
    from .nfo import sidecar_signature
    result = {'imported':0,'updated':0,'waiting':0,'offline':[],'errors':[]}
    for config in library.setting('watched_folders',[]):
        check_cancelled(cancelled)
        if not config.get('enabled',True): continue
        root = Path(config['path']).resolve()
        if not root.is_dir(): result['offline'].append(str(root));continue
        key = 'watch-state:'+hashlib.sha256((str(root)+config['kind']).encode()).hexdigest()
        previous = library.setting(key,{})
        state,ready,cache,signatures = {},[],{},{}
        for path in root.rglob('*'):
            check_cancelled(cancelled)
            if path.suffix.lower() not in VIDEO_EXTENSIONS or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root): continue
            try:
                stat = path.stat()
                signature = f'{stat.st_size}:{stat.st_mtime_ns}:'+sidecar_signature(path,root,config['kind'],cache,signatures)
                old = previous.get(str(path),{})
                current = {'signature':signature,'since':old.get('since',clock()) if old.get('signature')==signature else clock(),
                           'imported':old.get('imported')}
                state[str(path)] = current
                if current['imported']==signature: continue
                if old.get('signature')==signature and clock()-current['since'] >= config.get('settle_seconds',15) and clock()-stat.st_mtime >= config.get('settle_seconds',15):
                    ready.append(path)
                else: result['waiting']+=1
            except OSError as exc: result['errors'].append({'path':str(path),'reason':str(exc)})
        if ready:
            batch = library.import_folder(root,config['kind'],progress,fast=True,cancelled=cancelled,candidates=ready)
            result['imported']+=batch['imported'];result['updated']+=batch.get('nfo_updated',0)
            result['errors'].extend(batch['errors'])
            failed = {error['path'] for error in batch['errors']}
            for path in ready:
                if str(path) not in failed: state[str(path)]['imported']=state[str(path)]['signature']
        if state!=previous:library.set_setting(key,state)
    return result


def audit_library(library,progress=None,cancelled=None):
    from . import nfo
    report = {'checked':0,'issues':[],'duplicates':[],'created':now()}
    rows = [dict(row) for row in library.db.execute('SELECT f.*,w.thumbnail,w.title FROM files f JOIN works w ON w.id=f.work_id')]
    roots = {}
    groups = {}
    checked_nfo=set();checked_covers=set()
    for index,file in enumerate(rows):
        check_cancelled(cancelled)
        root = Path(file['root']);path=Path(file['path'])
        if str(root) not in roots: roots[str(root)]=root.is_dir()
        if not roots[str(root)]: status='directory_offline'
        elif not path.is_file(): status='file_missing'
        elif not path.resolve().is_relative_to(root.resolve()): status='outside_root'
        else: status=None
        if status: report['issues'].append({'kind':status,'file_id':file['id'],'path':str(path),'title':file['title']})
        else:
            if file['work_id'] not in checked_covers and (not file['thumbnail'] or not Path(file['thumbnail']).is_file()):
                report['issues'].append({'kind':'missing_cover','file_id':file['id'],'path':str(path),'title':file['title']})
            checked_covers.add(file['work_id'])
            sidecars={path.with_suffix('.nfo'),path.parent/'movie.nfo'}
            sidecars.update(parent/'tvshow.nfo' for parent in (path.parent,*path.parents) if parent.is_relative_to(root))
            for sidecar in sidecars:
                if sidecar not in checked_nfo and sidecar.is_file():
                    checked_nfo.add(sidecar)
                    try: nfo.read(sidecar)
                    except Exception as exc:
                        report['issues'].append({'kind':'invalid_nfo','file_id':file['id'],'path':str(sidecar),'reason':str(exc),'title':file['title']})
        if file['digest'] and not file['digest'].startswith('fast-'): groups.setdefault(file['digest'],[]).append(file['id'])
        report['checked']+=1
        if progress: progress(index+1,len(rows),'媒体体检 · '+str(path))
    report['duplicates']=[{'file_ids':ids,'basis':'full_sha256'} for ids in groups.values() if len(ids)>1]
    # Report only: never delete records or change a source video/NFO.
    library.set_setting('last_audit',report)
    return report
