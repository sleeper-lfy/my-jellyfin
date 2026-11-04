"""Explicit metadata list edits preserve unrelated fields and reject stale saves."""
import copy
import json


def normalize(field, values):
    if field not in {'tags', 'actors'} or not isinstance(values, list):
        raise ValueError('无效资料字段')
    result=[];seen=set()
    for value in values:
        if field=='tags':
            if not isinstance(value,str):raise ValueError('标签须为文字')
            item=value.strip();name=item
        else:
            if not isinstance(value,dict):raise ValueError('演员资料无效')
            item=copy.deepcopy(value);name=str(item.get('name','')).strip();item['name']=name
            if item.get('gender','unknown') not in {'female','male','unknown'}:raise ValueError('演员性别无效')
            if not isinstance(item.get('aliases',[]),list) or any(not isinstance(a,str) for a in item.get('aliases',[])):
                raise ValueError('演员别名须为文字列表')
            if 'aliases' in item:item['aliases']=list(dict.fromkeys(a.strip() for a in item['aliases'] if a.strip()))
        if not name or len(name)>200:raise ValueError('名称不能为空，且不能超过 200 个字符')
        if name.casefold() in seen:raise ValueError('名称重复：'+name)
        seen.add(name.casefold());result.append(item)
    return result


def snapshot(library, work_id):
    row=library.db.execute('SELECT metadata FROM works WHERE id=?',(work_id,)).fetchone()
    if not row:raise ValueError('影片已不存在')
    return json.loads(row[0])


def save_lists(library, work_id, changes, expected):
    cleaned={field:normalize(field,value) for field,value in changes.items()}
    # Acquire the write lock before reading: background scraping cannot interleave.
    with library.db:
        library.db.execute('BEGIN IMMEDIATE')
        row=library.db.execute('SELECT metadata,locked FROM works WHERE id=?',(work_id,)).fetchone()
        if not row:raise ValueError('影片已不存在')
        metadata=json.loads(row['metadata']);locked=json.loads(row['locked'])
        for field,values in cleaned.items():
            if metadata.get(field,[])!=expected.get(field,[]):
                raise ValueError('这项资料在编辑期间已更新，请关闭窗口后重新编辑')
            metadata[field]=values
            if field not in locked:locked.append(field)
        library.db.execute('UPDATE works SET metadata=?,locked=? WHERE id=?',
                           (json.dumps(metadata,ensure_ascii=False),json.dumps(locked),work_id))
