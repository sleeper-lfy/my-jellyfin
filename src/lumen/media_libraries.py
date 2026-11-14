"""Named media libraries; file membership survives moves and personal data stays on works."""
import json
import os
from pathlib import Path
from .organize_templates import validate_rule

KINDS = {'movie':'电影','series':'电视剧','vr':'VR 电影','fans':'Fans','other':'其他'}


def identifier(value):
    if type(value) is not int or value < 1:raise ValueError('无效媒体库编号')
    return value


def get(library, library_id):
    row=library.db.execute('SELECT * FROM media_libraries WHERE id=?',(identifier(library_id),)).fetchone()
    if not row:raise ValueError('媒体库不存在或已移除')
    return {**dict(row),'config':json.loads(row['config'])}


def list_libraries(library, *, public=False):
    rows=library.db.execute('''SELECT l.*,COUNT(DISTINCT f.work_id) AS count FROM media_libraries l
        LEFT JOIN media_library_files m ON m.library_id=l.id LEFT JOIN files f ON f.id=m.file_id
        GROUP BY l.id ORDER BY l.name COLLATE NOCASE,l.id''').fetchall()
    return [{key:row[key] for key in ('id','name','kind','count')} if public else
            {**dict(row),'config':json.loads(row['config'])} for row in rows]


def normalized(path):
    if not isinstance(path,str) or not path.strip() or not Path(path.strip()).is_absolute():raise ValueError('目录须为完整绝对路径')
    return str(Path(path.strip()).resolve())


def _path(value):
    # Imported paths are canonical; membership checks never wake offline drives.
    return Path(os.path.normcase(os.path.abspath(str(value))))


def overlaps(left,right):
    a,b=_path(left),_path(right)
    return a==b or a.is_relative_to(b) or b.is_relative_to(a)


def validate(library,name,kind,config,library_id=None,*,migrating=False):
    if not isinstance(name,str) or not name.strip() or len(name.strip())>80:raise ValueError('请输入 1–80 字的媒体库名称')
    if kind not in KINDS:raise ValueError('无效媒体类型')
    if not isinstance(config,dict):raise ValueError('无效媒体库配置')
    if library_id is not None and get(library,library_id)['kind']!=kind:raise ValueError('媒体库创建后不可更改类型，请新建媒体库')
    for row in list_libraries(library):
        if row['id']!=library_id and row['name'].casefold()==name.strip().casefold():raise ValueError('媒体库名称已存在')
    raw=config.get('roots',[])
    if not isinstance(raw,list) or len(raw)>100:raise ValueError('每库最多配置 100 个目录')
    roots=[]
    for entry in raw:
        if not isinstance(entry,dict) or type(entry.get('enabled',True)) is not bool:raise ValueError('无效目录监听设置')
        path=normalized(entry.get('path'))
        if any(overlaps(path,r['path']) for r in roots):raise ValueError('同一目录及其子目录不能重复添加')
        roots.append({'path':path,'enabled':entry.get('enabled',True)})
    if type(config.get('watch',True)) is not bool:raise ValueError('无效媒体库监听设置')
    settle=config.get('settle_seconds',15)
    if type(settle) is not int or not 5<=settle<=600:raise ValueError('稳定等待须为 5–600 秒')
    plugin=config.get('plugin','');fallbacks=config.get('fallback_plugins',[])
    if not isinstance(plugin,str) or len(plugin)>200 or not isinstance(fallbacks,list) or len(fallbacks)>7 or any(not isinstance(x,str) or not x or len(x)>200 for x in fallbacks):raise ValueError('来源或备用顺序无效，最多 7 个备用来源')
    if fallbacks and not plugin:raise ValueError('配置备用来源前须选择首选来源')
    destination=normalized(config['destination']) if config.get('destination') else ''
    clean={'roots':roots,'watch':config.get('watch',True),'settle_seconds':settle,'plugin':plugin,
           'fallback_plugins':list(dict.fromkeys(x for x in fallbacks if x!=plugin)),
           'destination':destination,'naming':validate_rule(config.get('naming',{}))}
    if kind not in {'movie','series','vr'} and (plugin or destination):raise ValueError('此类型仅扫描入库，不自动刮削或移动')
    mine=[r['path'] for r in roots]
    for other in list_libraries(library):
        if other['id']==library_id:continue
        theirs=[r['path'] for r in other['config']['roots']]
        other_target=other['config'].get('destination')
        if (any(overlaps(a,b) for a in mine for b in theirs)
            or other_target and any(overlaps(a,other_target) for a in mine)
            or destination and any(overlaps(destination,b) for b in theirs)):
            raise ValueError('监听目录与媒体库“'+other['name']+'”的目录或整理目标重叠')
    if not migrating:
        for old in library.setting('watched_folders',[]):
            if any(overlaps(p,str(Path(old['path']).resolve())) for p in [*mine,*([destination] if destination else [])]):raise ValueError('目录与旧监听配置重叠，请先迁移或移除旧监听配置')
    return name.strip(),clean


def _save(library,name,kind,config,library_id=None,*,migrating=False):
    name,config=validate(library,name,kind,config,library_id,migrating=migrating)
    if library_id is None:
        library_id=library.db.execute('INSERT INTO media_libraries(name,kind,config) VALUES (?,?,?)',(name,kind,json.dumps(config,ensure_ascii=False))).lastrowid
    else:library.db.execute('UPDATE media_libraries SET name=?,config=? WHERE id=?',(name,json.dumps(config,ensure_ascii=False),library_id))
    owned_paths=[r['path'] for r in config['roots']]
    for owned in library.db.execute('SELECT f.path,m.library_id FROM files f JOIN media_library_files m ON m.file_id=f.id').fetchall():
        if owned['library_id']!=library_id and any(_path(owned['path']).is_relative_to(_path(path)) for path in owned_paths):raise ValueError('目录包含已属于另一媒体库的文件')
    for row in library.db.execute('SELECT f.id,f.path FROM files f JOIN works w ON w.id=f.work_id WHERE w.kind=?',(kind,)).fetchall():
        if any(_path(row['path']).is_relative_to(_path(path)) for path in owned_paths):
            owner=library.db.execute('SELECT library_id FROM media_library_files WHERE file_id=?',(row['id'],)).fetchone()
            if owner and owner[0]!=library_id:raise ValueError('目录包含已属于另一媒体库的文件，请先核对归属')
            library.db.execute('INSERT OR IGNORE INTO media_library_files VALUES (?,?)',(row['id'],library_id))
    return library_id


def save(library,name,kind,config,library_id=None):
    with library.db:library_id=_save(library,name,kind,config,library_id)
    return get(library,library_id)


def remove(library,library_id):
    library.db.execute('BEGIN IMMEDIATE')
    try:
        get(library,library_id)
        if library.db.execute("SELECT 1 FROM tasks WHERE kind='ingest' AND status='running' AND json_extract(payload,'$.media_library_id')=?",(library_id,)).fetchone():raise ValueError('媒体库正在整理，请先停止任务再移除')
        library.db.execute('DELETE FROM media_libraries WHERE id=?',(library_id,))
        library.db.execute("UPDATE tasks SET status='cancelled' WHERE kind='ingest' AND status IN ('queued','retry','pending') AND json_extract(payload,'$.media_library_id')=?",(library_id,))
        library.db.commit()
    except BaseException:
        library.db.rollback();raise


def owner_for_path(library,path,kind=None,items=None):
    target=_path(path);outputs=[]
    for item in (list_libraries(library) if items is None else items):
        if kind is not None and item['kind']!=kind:continue
        if any(target.is_relative_to(_path(root['path'])) for root in item['config']['roots']):return item['id']
        destination=item['config'].get('destination')
        if destination and target.is_relative_to(_path(destination)):outputs.append(item['id'])
    # Shared output directories are valid; existing files retain explicit membership.
    # Never guess which library owns an unknown file in a shared output.
    return outputs[0] if len(outputs)==1 else None


def attach(library,file_id,library_id):
    if library_id is not None:
        owner=library.db.execute('SELECT library_id FROM media_library_files WHERE file_id=?',(file_id,)).fetchone()
        if owner and owner[0]!=library_id:raise ValueError('文件已属于另一媒体库，请先核对归属')
        library.db.execute('INSERT OR IGNORE INTO media_library_files VALUES (?,?)',(file_id,library_id))


def configs(library,library_id=None,*,legacy=True):
    result=list(library.setting('watched_folders',[])) if legacy and library_id is None else []
    for item in ([get(library,library_id)] if library_id else list_libraries(library)):
        rule=item['config']
        for root in rule['roots']:
            result.append({**rule,**root,'kind':item['kind'],'media_library_id':item['id'],
                           'enabled':rule['watch'] and root['enabled']})
    return result


def scan(library,library_id,progress=None,cancelled=None):
    from .directory_sync import scan_directories
    from .core import now, ImportCancelled
    item=get(library,library_id);key='media-library-scan:'+str(library_id)
    library.set_setting(key,{'status':'running','updated':now()})
    try:
        result=scan_directories(library,configs(library,library_id),progress,cancelled)
        from .ingestion import process_pending
        work_ids=[w['id'] for w in library.query({'media_library_id':library_id})]
        result['automation']=process_pending(library,progress,cancelled,work_ids=work_ids,media_library_id=library_id)
        library.set_setting(key,{'status':'done','updated':now(),'result':result})
        return result
    except BaseException as error:
        library.set_setting(key,{'status':'cancelled' if isinstance(error,ImportCancelled) else 'failed','updated':now(),'error':str(error)})
        raise


def migrate_legacy(library):
    """Explicit, atomic adoption; no metadata/file move and no lost directory overrides."""
    if library.setting('media-libraries-legacy-migrated',False):return []
    created=[]
    with library.db:
        grouped={}
        for entry in library.setting('watched_folders',[]):
            kind=entry['kind'];rule=library.setting('partition:'+kind,{})
            destination=entry.get('destination',rule.get('destination',''))
            from .organize_templates import load_rule
            config={'plugin':entry.get('plugin',rule.get('plugin','')),'destination':destination,
                    'fallback_plugins':library.setting('numbered_fallbacks:'+kind,[]) if entry.get('plugin',rule.get('plugin','')) else [],
                    'naming':load_rule(library,kind,destination) if destination else {},
                    'settle_seconds':entry.get('settle_seconds',library.setting('watch_settle_seconds',15))}
            key=(kind,json.dumps(config,sort_keys=True))
            bundle=grouped.setdefault(key,{**config,'roots':[]})
            bundle['roots'].append({'path':entry['path'],'enabled':entry.get('enabled',True)})
        for index,((kind,_),config) in enumerate(grouped.items()):
            name='原有'+KINDS[kind]+' · '+str(index+1)
            created.append(_save(library,name,kind,config,migrating=True))
        owners=list_libraries(library)
        for row in library.db.execute('SELECT f.id,f.path,w.kind FROM files f JOIN works w ON w.id=f.work_id WHERE NOT EXISTS(SELECT 1 FROM media_library_files m WHERE m.file_id=f.id)').fetchall():
            attach(library,row['id'],owner_for_path(library,row['path'],row['kind'],owners))
        for kind,title in KINDS.items():
            ids=[r[0] for r in library.db.execute('SELECT f.id FROM files f JOIN works w ON w.id=f.work_id WHERE w.kind=? AND NOT EXISTS(SELECT 1 FROM media_library_files m WHERE m.file_id=f.id)',(kind,))]
            if ids:
                media_id=_save(library,'原有'+title+'（未配置监听）',kind,{'watch':False},migrating=True);created.append(media_id)
                library.db.executemany('INSERT INTO media_library_files VALUES (?,?)',[(file_id,media_id) for file_id in ids])
        library.db.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)',[
            ('watched_folders','[]'),('media-libraries-legacy-migrated','true')])
    return created


def home_cards(library):
    memberships={}
    for row in library.db.execute('SELECT DISTINCT m.library_id,f.work_id FROM media_library_files m JOIN files f ON f.id=m.file_id'):
        memberships.setdefault(row[0],[]).append(row[1])
    return [{**item,'work_ids':memberships.get(item['id'],[])} for item in list_libraries(library,public=True)]


def work_libraries(library,work_id):
    return [row[0] for row in library.db.execute('SELECT DISTINCT m.library_id FROM media_library_files m JOIN files f ON f.id=m.file_id WHERE f.work_id=? ORDER BY m.library_id',(work_id,))]


def detach_work(library,library_id,work_id):
    library.db.execute('BEGIN IMMEDIATE')
    try:
        get(library,library_id);library.work(work_id,library_id)
        if library.db.execute("SELECT 1 FROM tasks WHERE kind='ingest' AND status='running' AND json_extract(payload,'$.media_library_id')=? AND json_extract(payload,'$.work_id')=?",(library_id,work_id)).fetchone():raise ValueError('此作品正在自动整理，请先停止任务')
        library.db.execute('DELETE FROM media_library_files WHERE library_id=? AND file_id IN (SELECT id FROM files WHERE work_id=?)',(library_id,work_id))
        library.db.execute("UPDATE tasks SET status='cancelled' WHERE kind='ingest' AND status IN ('queued','retry','pending') AND json_extract(payload,'$.media_library_id')=? AND json_extract(payload,'$.work_id')=?",(library_id,work_id))
        library.db.commit()
    except BaseException:
        library.db.rollback();raise
