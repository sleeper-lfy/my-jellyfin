"""Local creator collections: directory identity, no episodic or site matching."""
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from contextlib import nullcontext


def folder_for(path, root):
    """One first-level folder per creator; root-level clips form a root entry."""
    relative=Path(path).relative_to(root)
    return Path(root)/relative.parts[0] if len(relative.parts)>1 else Path(root)


def folder_key(folder):
    # Import roots are canonicalized once before scanning. Stored roots must
    # remain bindable during a metadata-only merge even when a disk is offline.
    return 'fans-folder:'+hashlib.sha256(os.path.normcase(os.path.abspath(os.fspath(folder))).encode()).hexdigest()


def roots_for(work):
    roots=work['metadata'].get('fans_roots',[])
    if isinstance(roots,list) and roots:return list(dict.fromkeys(str(Path(root)) for root in roots))
    return list(dict.fromkeys(str(folder_for(Path(file['path']),Path(file['root']))) for file in work['files']))


def target_for(library, folder, known=None):
    """Called inside the file's transaction; never match a creator by name."""
    from .core import now
    key=folder_key(folder)
    binding=library.db.execute('SELECT work_id FROM name_keys WHERE key=?',(key,)).fetchone()
    if binding:
        if known is not None and binding[0]!=known:raise ValueError('此目录已有独立的 Fans 作者条目，请先手动合并作者目录')
        known=binding[0]
    if known is None:
        cursor=library.db.execute('INSERT INTO works(identity,kind,title,metadata,added) VALUES (?,?,?,?,?)',
            (key,'fans',folder.name or str(folder),json.dumps({'creator':folder.name or str(folder),'fans_roots':[str(folder)]},ensure_ascii=False),now()))
        known=cursor.lastrowid
    work=library.work(known)
    if work['kind']!='fans':raise ValueError('作者目录与其他分类冲突，未改变原分类')
    metadata=work['metadata'];metadata['creator']=metadata.get('creator') or work['title']
    metadata['fans_roots']=list(dict.fromkeys([*roots_for(work),str(folder)]))
    library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),known))
    library.db.execute('INSERT OR IGNORE INTO name_keys VALUES (?,?)',(key,known))
    return known


def adopt_other(library, file, target):
    """An explicit Fans import can reclassify an existing loose-video record."""
    source=library.work(file['work_id'])
    if source['kind']!='other':raise ValueError('该视频已在电影、电视剧或 VR 分类中，请先核对分类；原记录已保留')
    if len(source['files'])==1:
        # This temporary change and the normal lossless merge are one atomic
        # transaction. No mixed-kind merge is exposed to generic callers.
        library.db.execute("UPDATE works SET kind='fans' WHERE id=?",(source['id'],))
        library.merge_works(source['id'],target,commit=False)
    else:
        destination=library.work(target)
        preference=destination if destination['favorite'] or destination['disliked'] else source
        library.db.execute('UPDATE works SET rating=?,favorite=?,liked=?,disliked=?,watchlist=?,thumbnail=COALESCE(thumbnail,?) WHERE id=?',
            (destination['rating'] if destination['rating'] is not None else source['rating'],preference['favorite'],preference['favorite'],preference['disliked'],
             max(destination['watchlist'],source['watchlist']),source['thumbnail'],target))
        library.db.execute('UPDATE files SET work_id=? WHERE id=?',(target,file['id']))
        queue=library.setting('queue')
        if queue and source['id'] in queue['ids'] and target not in queue['ids']:
            index=queue.get('index',0);current=queue['ids'][index] if 0<=index<len(queue['ids']) else None
            queue['ids'].insert(queue['ids'].index(source['id'])+1,target)
            queue['index']=queue['ids'].index(current) if current in queue['ids'] else len(queue['ids'])
            library.db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(queue),'queue'))
    library.db.execute('UPDATE files SET season=NULL,episode=NULL WHERE id=?',(file['id'],))


def import_folder(library, root, progress=None, fast=False, cancelled=None, candidates=None):
    from .core import VIDEO_EXTENSIONS,ImportCancelled,check_cancelled,quick_fingerprint,fingerprint,probe,thumbnail
    from .series import natural_key
    root=Path(root).resolve(strict=True)
    if not root.is_dir():raise ValueError('请选择文件夹')
    task=uuid.uuid4().hex;payload={'root':str(root),'kind':'fans','fast':fast}
    result={'imported':0,'duplicates':0,'errors':[],'warnings':[]}
    saved=[0]
    def report(done,total,stage,path='',force=False):
        payload['progress']={'completed':done,'total':total,'stage':stage,'path':str(path)}
        if force or time.monotonic()-saved[0]>=1:
            library.task(task,'import','running',payload,result);saved[0]=time.monotonic()
        if progress:progress(done,total,stage+(' · '+str(path) if path else ''))
    try:
        report(0,0,'扫描 Fans 作者目录',root,True)
        paths=[];last_scan=time.monotonic()
        for candidate in root.rglob('*') if candidates is None else map(Path,candidates):
            check_cancelled(cancelled)
            if candidate.is_file() and not candidate.is_symlink() and candidate.suffix.lower() in VIDEO_EXTENSIONS and root in candidate.resolve().parents:paths.append(candidate)
            if time.monotonic()-last_scan>=.25:
                report(0,0,f'扫描作者目录，已找到 {len(paths)} 个视频',candidate);last_scan=time.monotonic()
        paths.sort(key=natural_key)
        groups={}
        for number,path in enumerate(paths):
            check_cancelled(cancelled)
            report(0,len(paths),f'识别作者目录 {number+1} / {len(paths)}',path)
            folder=folder_for(path,root);group=groups.setdefault(folder,{'known':set()})
            row=library.db.execute("SELECT f.work_id FROM files f JOIN works w ON w.id=f.work_id WHERE f.path=? AND w.kind='fans'",(str(path),)).fetchone()
            if row:group['known'].add(row[0])
        for index,path in enumerate(paths):
            done=False
            try:
                check_cancelled(cancelled);report(index,len(paths),'索引作者视频',path)
                folder=folder_for(path,root);known=groups[folder]['known']
                if len(known)>1:raise ValueError('此作者目录包含多个独立 Fans 条目，请先手动合并')
                known_id=next(iter(known),None)
                stat=path.stat()
                row=library.db.execute('SELECT f.*,w.kind FROM files f JOIN works w ON w.id=f.work_id WHERE f.path=?',(str(path),)).fetchone()
                existing=dict(row) if row else None
                if existing and existing['kind'] not in {'fans','other'}:
                    raise ValueError('该视频已在电影、电视剧或 VR 分类中，未改变原记录；请选择未归档视频或先核对分类')
                cache=library.db.execute('SELECT * FROM import_cache WHERE file_id=?',(existing['id'],)).fetchone() if existing else None
                unchanged=cache and (cache['size'],cache['modified'])==(stat.st_size,stat.st_mtime_ns)
                if existing:
                    quick=quick_fingerprint(path) if fast and not unchanged else None
                    with library.db:
                        work_id=target_for(library,folder,known_id or (existing['work_id'] if existing['kind']=='fans' else None))
                        if existing['kind']=='other':adopt_other(library,existing,work_id)
                        if fast and (not unchanged or cache is None):
                            changed=cache is not None and not unchanged
                            if changed:library.db.execute('UPDATE files SET digest=?,duration=0 WHERE id=?',('fast-'+uuid.uuid4().hex,existing['id']))
                            library.db.execute('INSERT OR REPLACE INTO import_cache VALUES (?,?,?,?,?,?,?)',
                                (existing['id'],stat.st_size,stat.st_mtime_ns,quick,None,'fans-v1',1 if changed or existing['duration']<=0 else 0))
                    groups[folder]['known']={work_id}
                    if existing['kind']=='other':result['imported']+=1;result['reclassified']=result.get('reclassified',0)+1
                    else:result['duplicates']+=1
                    done=True;continue
                if fast:
                    quick=quick_fingerprint(path)
                    digest='fast-'+uuid.uuid4().hex;duration=0
                else:
                    digest=fingerprint(path,lambda amount,total:report(index,len(paths),f'计算指纹 {amount*100//max(1,total)}%',path),cancelled)
                    duration=probe(path,cancelled=cancelled) if cancelled else probe(path)
                cover=library.directory/'cache'/(digest+'.jpg')
                if not fast:
                    try:thumbnail(path,cover,duration,cancelled=cancelled) if cancelled else thumbnail(path,cover,duration)
                    except ImportCancelled:raise
                    except Exception as error:result['warnings'].append({'path':str(path),'reason':'缩略图: '+str(error)})
                with library.db:
                    work_id=target_for(library,folder,known_id)
                    cursor=library.db.execute('INSERT INTO files(work_id,path,digest,root,season,episode,duration) VALUES (?,?,?,?,NULL,NULL,?)',
                        (work_id,str(path),digest,str(root),duration))
                    if fast:library.db.execute('INSERT INTO import_cache VALUES (?,?,?,?,?,?,?)',(cursor.lastrowid,stat.st_size,stat.st_mtime_ns,quick,None,'fans-v1',1))
                    if cover.is_file():library.db.execute('UPDATE works SET thumbnail=COALESCE(thumbnail,?) WHERE id=?',(str(cover),work_id))
                groups[folder]['known']={work_id};result['imported']+=1;done=True
            except ImportCancelled:raise
            except Exception as error:result['errors'].append({'path':str(path),'reason':str(error)});done=True
            finally:
                report(index+int(done),len(paths),f"已处理 · 导入 {result['imported']} · 重复 {result['duplicates']} · 失败 {len(result['errors'])}",path)
        report(len(paths),len(paths),'处理完成' if paths else '没有找到视频',force=True)
        library.task(task,'import','partial' if result['errors'] else 'done',payload,result)
    except ImportCancelled:
        result['cancelled']=True;library.task(task,'import','cancelled',payload,result)
    except Exception as error:
        library.task(task,'import','failed',payload,result,str(error));raise
    return result


def merge_folders(library, work_ids, target_id, creator=None, *, commit=True):
    if type(target_id) is not int or not isinstance(work_ids,list) or not work_ids or len(work_ids)>1000 or any(type(work_id) is not int for work_id in work_ids):
        raise ValueError('请选择有效的 Fans 作者条目')
    if creator is not None and (not isinstance(creator,str) or not creator.strip() or len(creator.strip())>200):raise ValueError('作者名称须为 1–200 个字符')
    ids=list(dict.fromkeys([target_id,*work_ids]))
    with library.db if commit else nullcontext():
        if not library.db.in_transaction:library.db.execute('BEGIN IMMEDIATE')
        works=[library.work(work_id) for work_id in ids]
        if any(work['kind']!='fans' for work in works):raise ValueError('只能合并 Fans 作者目录，不能与影视或其他分类混合')
        roots=list(dict.fromkeys(root for work in works for root in roots_for(work)))
        for root in roots:
            bound=library.db.execute('SELECT work_id FROM name_keys WHERE key=?',(folder_key(root),)).fetchone()
            if bound and bound[0] not in ids:raise ValueError('所选目录已属于另一个 Fans 作者，请先核对目录关联')
        for work_id in ids:
            if work_id!=target_id:library.merge_works(work_id,target_id,commit=False)
        target=library.work(target_id);metadata=target['metadata'];metadata['fans_roots']=roots
        name=creator.strip() if creator is not None else metadata.get('creator') or target['title']
        if target['title']!=name:metadata['aliases']=list(dict.fromkeys([*metadata.get('aliases',[]),target['title']]))
        metadata['creator']=name
        library.db.execute('UPDATE works SET title=?,metadata=? WHERE id=?',(name,json.dumps(metadata,ensure_ascii=False),target_id))
        library.db.executemany('INSERT INTO name_keys VALUES (?,?) ON CONFLICT(key) DO UPDATE SET work_id=excluded.work_id',[(folder_key(root),target_id) for root in roots])
    return {'work_id':target_id,'merged':len(ids)-1,'files':len(library.work(target_id)['files']),'creator':name,'roots':roots}
