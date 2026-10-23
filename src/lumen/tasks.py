"""Bounded task summaries; full reports never enter the table or GUI JSON parser."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from .core import check_cancelled


@contextmanager
def database(directory):
    connection=sqlite3.connect(Path(directory)/'library.sqlite',timeout=.3)
    connection.row_factory=sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        yield connection
    finally:connection.close()


def snapshot(directory,offset=0):
    with database(directory) as db:
        rows=db.execute('''SELECT id,kind,status,updated,substr(error,1,2000) AS error,
             CASE WHEN length(payload)<=32768 THEN payload ELSE '{}' END AS payload,
             substr(result,1,240) AS result,length(payload)+length(result) AS report_size
             FROM tasks ORDER BY updated DESC,id DESC LIMIT 100 OFFSET ?''',(max(0,int(offset)),)).fetchall()
    output=[]
    for row in rows:
        item=dict(row)
        try:
            result=json.loads(item['result'])
            if isinstance(result,dict) and 'imported' in result:
                item['result']=f"导入 {result['imported']} · 重复 {result.get('duplicates',0)} · 失败 {len(result.get('errors',[]))} · 警告 {len(result.get('warnings',[]))}"
        except (ValueError,TypeError):item['result']='结果已保存，可查看详情或导出完整记录'
        output.append(item)
    return output


def record(directory,identifier,preview=False,retry=False):
    with database(directory) as db:
        if preview:
            row=db.execute('''SELECT id,kind,status,updated,substr(error,1,4000) AS error,
                substr(payload,1,65536) AS payload,substr(result,1,131072) AS result,
                length(payload) AS payload_size,length(result) AS result_size FROM tasks WHERE id=?''',(identifier,)).fetchone()
        else:row=db.execute('SELECT * FROM tasks WHERE id=?',(identifier,)).fetchone()
    if not row:raise ValueError('任务已不存在')
    result=dict(row)
    if preview:
        truncated=result.pop('payload_size')>65536
        truncated=(result.pop('result_size')>131072) or truncated
        for field in ('payload','result'):
            try:result[field]=json.loads(result[field])
            except (ValueError,TypeError):pass
        text=json.dumps(result,ensure_ascii=False,indent=2)
        return {'text':text[:220000],'truncated':truncated or len(text)>220000}
    if retry:
        result['payload']=json.loads(result['payload'])
        result['candidates']=[error['path'] for error in json.loads(result['result']).get('errors',[]) if error.get('path')] if result['kind']=='import' else None
        result.pop('result',None)
    return result


def export(directory,identifier,destination,cancelled=None):
    destination=Path(destination);temporary=destination.with_name(destination.name+'.part')
    try:
        with database(directory) as db,temporary.open('w',encoding='utf-8') as output:
            db.execute('BEGIN')
            row=db.execute('SELECT id,kind,status,updated,error,length(payload),length(result) FROM tasks WHERE id=?',(identifier,)).fetchone()
            if not row:raise ValueError('任务已不存在')
            output.write(json.dumps({key:row[key] for key in ('id','kind','status','updated','error')},ensure_ascii=False)[:-1])
            for field,length in (('payload',row[5]),('result',row[6])):
                output.write(',"'+field+'":')
                for offset in range(1,length+1,65536):
                    check_cancelled(cancelled)
                    output.write(db.execute(f'SELECT substr({field},?,65536) FROM tasks WHERE id=?',(offset,identifier)).fetchone()[0])
            output.write('}')
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
    return str(destination)
