"""Transactional, entity-scoped previews and persistent manual merge undo."""
import json
import sqlite3
import uuid
from .core import now


TABLES = ('works', 'sources', 'name_keys', 'external_ids')


def state(library, ids):
    marks=','.join('?' for _ in ids)
    result={}
    for table in TABLES:
        column='id' if table=='works' else 'work_id'
        rows=[dict(row) for row in library.db.execute(f'SELECT * FROM {table} WHERE {column} IN ({marks})',ids)]
        result[table]=sorted(rows,key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False))
    result['files']=[dict(row) for row in library.db.execute(f'SELECT id,path,work_id FROM files WHERE work_id IN ({marks}) ORDER BY id',ids)]
    result['artwork']={str(work_id):library.setting(f'artwork_{work_id}') for work_id in ids}
    return result


def perform(library, source_ids, target_id, creator=None):
    target=library.work(target_id)
    if target['kind']=='fans':
        from .fans import merge_folders
        return merge_folders(library,source_ids,target_id,creator,commit=False)
    if creator is not None:raise ValueError('只有 Fans 作者合并可修改作者名称')
    for source_id in source_ids:library.merge_works(source_id,target_id,commit=False)
    return {'work_id':target_id,'merged':len(source_ids),'files':len(library.work(target_id)['files'])}


def identifiers(source_ids,target_id):
    if type(target_id) is not int or not isinstance(source_ids,list) or not source_ids or len(source_ids)>1000 or any(type(value) is not int for value in source_ids):
        raise ValueError('请选择有效的合并条目')
    sources=list(dict.fromkeys(value for value in source_ids if value!=target_id))
    if not sources:raise ValueError('请至少选择一个其他条目')
    return sources,[target_id,*sources]


def preview_merge(library,source_ids,target_id,creator=None):
    sources,ids=identifiers(source_ids,target_id)
    library.db.execute('SAVEPOINT merge_preview')
    try:
        before=state(library,ids)
        originals=[library.work(work_id) for work_id in ids]
        result=perform(library,sources,target_id,creator)
        after=library.work(target_id)
        return {'source_ids':sources,'target_id':target_id,'creator':creator,'before':before,
                'originals':originals,'result':after,'summary':result}
    finally:
        library.db.execute('ROLLBACK TO merge_preview')
        library.db.execute('RELEASE merge_preview')


def apply_merge(library,preview):
    sources,ids=identifiers(preview['source_ids'],preview['target_id'])
    with library.db:
        library.db.execute('BEGIN IMMEDIATE')
        if state(library,ids)!=preview['before']:
            raise ValueError('条目在预览后已发生变化，请重新预览再合并')
        queue_before=library.setting('queue')
        result=perform(library,sources,preview['target_id'],preview.get('creator'))
        identifier=uuid.uuid4().hex
        record={'version':1,'id':identifier,'created':now(),'status':'merged','target_id':preview['target_id'],
                'source_ids':sources,'titles':[work['title'] for work in preview['originals']],
                'before':preview['before'],'after':state(library,ids),
                'queue_before':queue_before,'queue_after':library.setting('queue')}
        library.db.execute('INSERT INTO settings VALUES (?,?)',('merge-history:'+identifier,json.dumps(record,ensure_ascii=False)))
    return {**result,'updated':True,'merge_id':identifier}


def records(library,target_id):
    found=[]
    for row in library.db.execute("SELECT value FROM settings WHERE key LIKE 'merge-history:%'"):
        record=json.loads(row[0])
        if record['target_id']==target_id:found.append(record)
    return sorted(found,key=lambda record:(record['created'],record['id']),reverse=True)


def undo_merge(library,identifier):
    try:
        with library.db:
            library.db.execute('BEGIN IMMEDIATE')
            row=library.db.execute('SELECT value FROM settings WHERE key=?',('merge-history:'+identifier,)).fetchone()
            if not row:raise ValueError('合并记录不存在')
            record=json.loads(row[0]);ids=[record['target_id'],*record['source_ids']]
            if record.get('version')!=1:raise ValueError('此合并记录版本暂不支持撤销')
            if record['status']!='merged':raise ValueError('此合并已经撤销')
            if state(library,ids)!=record['after']:
                raise ValueError('合并后资料、图片选择或文件归属已改变，无法安全撤销；请先核对后续操作')
            before=record['before'];marks=','.join('?' for _ in ids)
            for table in TABLES[1:]:library.db.execute(f'DELETE FROM {table} WHERE work_id IN ({marks})',ids)
            columns=[row['name'] for row in library.db.execute('PRAGMA table_info(works)')]
            if any(set(work)!=set(columns) for work in before['works']):raise ValueError('资料库结构已更新，此合并记录暂不能撤销')
            for work in before['works']:
                if library.db.execute('SELECT 1 FROM works WHERE id=?',(work['id'],)).fetchone():
                    fields=[column for column in columns if column!='id']
                    library.db.execute('UPDATE works SET '+','.join(f'{column}=?' for column in fields)+' WHERE id=?',[*[work[column] for column in fields],work['id']])
                else:
                    library.db.execute('INSERT INTO works ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',[work[column] for column in columns])
            for file in before['files']:
                library.db.execute('UPDATE files SET work_id=? WHERE id=?',(file['work_id'],file['id']))
            for table in TABLES[1:]:
                for entry in before[table]:
                    fields=list(entry)
                    library.db.execute(f'INSERT INTO {table} ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',[entry[field] for field in fields])
            for work_id,value in before['artwork'].items():
                if value is None:library.db.execute('DELETE FROM settings WHERE key=?',('artwork_'+work_id,))
                else:library.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('artwork_'+work_id,json.dumps(value,ensure_ascii=False)))
            if library.setting('queue')==record['queue_after']:
                if record['queue_before'] is None:library.db.execute("DELETE FROM settings WHERE key='queue'")
                else:library.db.execute("INSERT OR REPLACE INTO settings VALUES ('queue',?)",(json.dumps(record['queue_before'],ensure_ascii=False),))
            record.update(status='undone',undone=now())
            library.db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(record,ensure_ascii=False),'merge-history:'+identifier))
    except sqlite3.IntegrityError as error:
        raise ValueError('原条目的编号或索引已被占用，未执行撤销，请人工核对') from error
    return {'updated':True,'work_id':record['target_id'],'restored':len(record['source_ids'])}
