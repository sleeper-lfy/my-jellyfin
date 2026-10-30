"""Conservative automatic portrait matching using enabled actor providers."""
import json
from pathlib import Path
import time
import unicodedata

from .core import ImportCancelled, check_cancelled
from .plugins import Plugins


def normalized(name):
    return ' '.join(unicodedata.normalize('NFKC', name).casefold().split())


def actor_targets(library, names=None, *, replace=False, cancelled=None):
    selected=None if names is None else {name.strip().casefold() for name in names}
    targets={}
    for row in library.db.execute('SELECT id,metadata,locked FROM works ORDER BY id'):
        check_cancelled(cancelled)
        locked='actors' in json.loads(row['locked'])
        for actor in json.loads(row['metadata']).get('actors', []):
            name=actor.get('name','').strip()
            if not name:continue
            key=name.casefold()
            if selected is not None and key not in selected:continue
            record=targets.setdefault(key,{'name':name,'aliases':set(),'work_ids':set(),'eligible':False})
            record['aliases'].update(alias for alias in actor.get('aliases',[]) if isinstance(alias,str) and alias.strip())
            record['work_ids'].add(row['id'])
            if not locked and (replace or not actor.get('photo_cache') or not Path(actor['photo_cache']).is_file()):
                record['eligible']=True
    return list(targets.values())


def unique_candidate(records, target):
    wanted={normalized(name) for name in [target['name'], *target['aliases']]}
    matches={}
    for record in records:
        names={normalized(name) for name in [record['name'], *record.get('aliases',[])]}
        if wanted & names:
            # Repeated provider rows for the same identity are one candidate.
            matches.setdefault(str(record['id']),record)
    if len(matches)>1:return None,'ambiguous'
    if not matches:return None,'unmatched'
    record=next(iter(matches.values()))
    return (record,'matched') if record.get('photo') else (None,'no_photo')


def fetch_actor_portraits(library, plugin_ids, *, names=None, replace=False, progress=None, cancelled=None, delay=.5):
    manager=Plugins(library)
    enabled={p['id'] for p in manager.installed() if p['config'].get('enabled') and 'actors' in p['capabilities']}
    plugin_ids=list(dict.fromkeys(plugin_ids))
    if not plugin_ids or any(identifier not in enabled for identifier in plugin_ids):
        raise ValueError('请选择已启用且支持演员头像的插件')
    result={'updated':0,'updated_works':0,'skipped':0,'ambiguous':0,'unmatched':0,'failed':0,
            'cancelled':False,'items':[],'total':0,'completed':0}
    next_request=0
    try:
        targets=actor_targets(library,names,replace=replace,cancelled=cancelled)
        result['total']=len(targets)
        for target in targets:
            check_cancelled(cancelled)
            entry={'name':target['name'],'status':'skipped','reason':'已有头像或演员资料已锁定','attempts':[]}
            if target['eligible']:
                statuses=[]
                for plugin_id in plugin_ids:
                    check_cancelled(cancelled)
                    while time.monotonic()<next_request:
                        check_cancelled(cancelled);time.sleep(min(.05,max(0,next_request-time.monotonic())))
                    if progress:progress(result['completed'],result['total'],'搜索 '+target['name'])
                    try:
                        records=manager.run(plugin_id,'actors',query=target['name'],cancelled=cancelled)
                        next_request=time.monotonic()+delay
                        candidate,status=unique_candidate(records,target)
                        if candidate is not None:
                            saved=manager.merge_actor(plugin_id,candidate,target['name'],replace=replace,
                                exact_name=True,work_ids=target['work_ids'],cancelled=cancelled)
                            entry.update(status='updated' if saved['updated'] else 'skipped',plugin=plugin_id,
                                reason='已保存头像' if saved['updated'] else '资料已变化，无需更新')
                            result['updated_works']+=saved['updated']
                            break
                        statuses.append(status);entry['attempts'].append({'plugin':plugin_id,'status':status})
                    except ImportCancelled:raise
                    except Exception as error:
                        next_request=time.monotonic()+delay
                        statuses.append('failed');entry['attempts'].append({'plugin':plugin_id,'status':'failed','error':str(error)[:600]})
                else:
                    status='ambiguous' if 'ambiguous' in statuses else 'failed' if 'failed' in statuses else 'unmatched'
                    entry.update(status=status,reason={'ambiguous':'同名或别名匹配到多个人，请手动确认',
                        'failed':'来源请求或保存失败，可重试','unmatched':'没有找到姓名或别名完全匹配且有头像的资料'}[status])
            result[entry['status']]+=1;result['completed']+=1;result['items'].append(entry)
            if progress:progress(result['completed'],result['total'],target['name']+' · '+entry['reason'])
    except ImportCancelled:
        result['cancelled']=True
    return result
