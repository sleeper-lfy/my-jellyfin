"""Manual library-directory synchronization with explicit missing-record cleanup."""
import os
import time
from pathlib import Path
from .core import VIDEO_EXTENSIONS, check_cancelled
from .ingestion import enqueue


def scan_tree(root,cancelled=None):
    if not root.is_dir():raise OSError('目录不可用或已离线')
    videos=[]
    def failed(error):raise error
    for folder,dirs,files in os.walk(root,onerror=failed,followlinks=False):
        check_cancelled(cancelled)
        dirs[:]=[name for name in dirs if not (Path(folder)/name).is_symlink()]
        for name in files:
            path=Path(folder)/name
            if path.suffix.lower() in VIDEO_EXTENSIONS and not path.is_symlink():
                videos.append(path)
    if not root.is_dir():raise OSError('扫描期间目录已离线')
    return videos


def scan_directories(library,configs,progress=None,cancelled=None,clock=time.time):
    result={'imported':0,'updated':0,'waiting':0,'missing':[],'offline':[],'errors':[]}
    for index,config in enumerate(configs):
        check_cancelled(cancelled)
        root=Path(config['path']).resolve();kind=config['kind']
        if progress:progress(index,len(configs),'刷新目录 · '+str(root))
        try:
            videos=scan_tree(root,cancelled)
            ready=[]
            for path in videos:
                check_cancelled(cancelled)
                if clock()-path.stat().st_mtime>=config.get('settle_seconds',15):ready.append(path)
                else:result['waiting']+=1
            batch=library.import_folder(root,kind,progress,fast=True,candidates=ready,cancelled=cancelled) if ready else {'imported':0,'errors':[]}
            result['imported']+=batch['imported'];result['updated']+=batch.get('nfo_updated',0);result['errors'].extend(batch['errors'])
            rule=library.setting('partition:'+kind,{})
            for work in library.query({'kinds':[kind],'folder':str(root),**({'media_library_id':config['media_library_id']} if 'media_library_id' in config else {})}):
                enqueue(library,work,config.get('plugin',rule.get('plugin','')),config.get('destination',rule.get('destination','')), **({'fallback_plugins':config['fallback_plugins'],'media_library_id':config['media_library_id'],'naming_rule':config['naming']} if 'media_library_id' in config else {}))
            # Only a complete, readable directory scan may propose missing records.
            rows=library.db.execute('SELECT f.id,f.work_id,f.path,w.title FROM files f JOIN works w ON w.id=f.work_id WHERE w.kind=?',(kind,)).fetchall()
            missing=[]
            for row in rows:
                path=Path(row['path'])
                if not path.is_relative_to(root):continue
                try:path.stat()
                except FileNotFoundError:missing.append({**dict(row),'root':str(root)})
            if not root.is_dir():raise OSError('扫描期间目录已离线')
            result['missing'].extend(missing)
        except OSError as error:
            result['offline'].append({'path':str(root),'reason':str(error)})
    return result


def remove_missing(library,entries,cancelled=None):
    removed=0;skipped=0;groups={}
    # Recheck complete root accessibility before removing any records from it.
    online=set()
    for root in {entry['root'] for entry in entries}:
        check_cancelled(cancelled)
        try:scan_tree(Path(root),cancelled);online.add(root)
        except OSError:pass
    for entry in entries:
        check_cancelled(cancelled)
        row=library.db.execute('SELECT id,work_id,path FROM files WHERE id=?',(entry['id'],)).fetchone()
        if not row or entry['root'] not in online or row['path']!=entry['path'] or row['work_id']!=entry['work_id']:
            skipped+=1;continue
        if not Path(row['path']).is_relative_to(Path(entry['root'])) or library.db.execute('SELECT 1 FROM sessions WHERE file_id=? AND ended IS NULL',(row['id'],)).fetchone():
            skipped+=1;continue
        try:Path(row['path']).stat()
        except FileNotFoundError:
            if Path(entry['root']).is_dir():groups.setdefault(row['work_id'],[]).append(row['id']);continue
        except OSError:pass
        skipped+=1
    for work_id,identifiers in groups.items():
        check_cancelled(cancelled)
        removed+=library.remove_local_records(work_id,identifiers)['removed']
    return {'removed':removed,'skipped':skipped}
