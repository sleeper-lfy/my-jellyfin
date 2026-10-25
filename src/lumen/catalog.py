"""Catalog actions shared by desktop and LAN clients; never delete media files."""
import json
import time
from pathlib import Path

SORTS = {'added','title','year','rating','duration'}


def watch_state(files):
    if files and all(f['completed'] for f in files): return 'completed'
    if any(f['completed'] or f['position'] > 0 for f in files): return 'progress'
    return 'unwatched'


def sort_items(items, field='added', descending=True):
    if field not in SORTS: raise ValueError('无效排序字段')
    def value(w):
        if field == 'duration': return sum(f['duration'] for f in w['files'])
        if field == 'title': return w['title'].casefold()
        return w.get(field)
    known=[w for w in items if value(w) is not None]
    missing=[w for w in items if value(w) is None]
    known.sort(key=lambda w:w['id'])
    known.sort(key=value,reverse=descending)
    return known+missing

def validate_filters(filters):
    if not isinstance(filters,dict):raise ValueError('无效筛选条件')
    list_keys={'kinds','tags_all','tags_any','tags_not','ids'}
    string_keys={'query','actor','folder','sort','watch_state','watched'}
    numeric={'year_min','year_max','rating_min','rating_max'}
    boolean={'favorite','watchlist','disliked','local','continue','female_cast','descending'}
    if not filters.keys()<=list_keys|string_keys|numeric|boolean:raise ValueError('未知筛选字段')
    for k,v in filters.items():
        if k in list_keys and (not isinstance(v,list) or len(v)>1000 or any((type(x) is not int if k=='ids' else not isinstance(x,str)) for x in v)):raise ValueError('无效筛选列表')
        if k in string_keys and (not isinstance(v,str) or len(v)>2000):raise ValueError('无效筛选文本')
        if k in numeric and v is not None and (type(v) is not int or not 0<=v<=9999):raise ValueError('无效筛选数值')
        if k in boolean and type(v) is not bool:raise ValueError('无效筛选标记')
    if filters.get('sort','added') not in SORTS:raise ValueError('无效排序')
    if filters.get('watch_state','') not in {'','unwatched','progress','completed'}:raise ValueError('无效观看状态')


class CatalogActions:
    def set_watched(self, work_id, state, file_id=None):
        if not isinstance(state,str) or state not in {'completed','unwatched','reset'}: raise ValueError('无效观看状态')
        if file_id is not None and type(file_id) is not int:raise ValueError('无效视频编号')
        work=self.work(work_id)
        files=[f for f in work['files'] if file_id is None or f['id']==file_id]
        if not files: raise ValueError('视频不存在')
        with self.db:
            for f in files:
                self.db.execute('UPDATE files SET position=0,completed=? WHERE id=?',(int(state=='completed'),f['id']))
                self._stamp_file_state(f['id'])
        # Session/activity rows remain real viewing records, never fabricated.

    def batch_catalog(self, ids, action, value=None):
        if not isinstance(ids,list) or any(type(i) is not int for i in ids):raise ValueError('无效作品编号')
        ids=list(dict.fromkeys(ids))
        if not ids or len(ids)>1000: raise ValueError('请选择 1–1000 部作品')
        works=[self.work(i) for i in ids]
        if action not in {'favorite','watchlist','completed','unwatched','tags'}:raise ValueError('无效批量操作')
        if action=='tags' and (not isinstance(value,list) or any(not isinstance(t,str) or len(t)>100 for t in value)):raise ValueError('无效标签')
        with self.db:
            for w in works:
                if action in {'favorite','watchlist'}:
                    if type(value) is not bool:raise ValueError('标记须为布尔值')
                    if action=='favorite':self.db.execute('UPDATE works SET favorite=?,liked=?,disliked=CASE WHEN ? THEN 0 ELSE disliked END WHERE id=?',(value,value,value,w['id']))
                    else:self.db.execute('UPDATE works SET watchlist=? WHERE id=?',(value,w['id']))
                elif action=='tags':
                    metadata=w['metadata'];metadata['tags']=list(dict.fromkeys([*metadata.get('tags',[]),*value]))
                    self.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),w['id']))
                else:
                    self.db.execute('UPDATE files SET completed=?,position=0 WHERE work_id=?',(int(action=='completed'),w['id']))
                    for f in w['files']:self._stamp_file_state(f['id'])

    def _stamp_file_state(self,file_id):
        # Manual reset/completion takes precedence over an older queued sample
        # or an exit recovery file written before the user's explicit action.
        stamp=json.dumps(time.time_ns())
        self.db.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)',[(prefix+str(file_id),stamp) for prefix in ('playback-position:','playback-state:')])

    def remove_catalog(self, work_id):
        self.work(work_id)
        if self.db.execute('SELECT 1 FROM sessions s JOIN files f ON f.id=s.file_id WHERE f.work_id=? AND s.ended IS NULL',(work_id,)).fetchone():raise ValueError('请先停止该作品的播放会话，再移出媒体库')
        with self.db:
            self.db.execute('DELETE FROM activity WHERE session_id IN (SELECT s.id FROM sessions s JOIN files f ON f.id=s.file_id WHERE f.work_id=?)',(work_id,))
            self.db.execute('DELETE FROM sessions WHERE file_id IN (SELECT id FROM files WHERE work_id=?)',(work_id,))
            for table in ('sources','name_keys','external_ids'):self.db.execute(f'DELETE FROM {table} WHERE work_id=?',(work_id,))
            self.db.execute('DELETE FROM files WHERE work_id=?',(work_id,))
            self.db.execute('DELETE FROM works WHERE id=?',(work_id,))
        queue=self.setting('queue',{'ids':[],'index':0})
        self.edit_queue([i for i in queue['ids'] if i!=work_id])

    def relocate_root(self, old_root, new_root, progress=None):
        from .core import fingerprint, check_cancelled
        old,new=Path(old_root).resolve(),Path(new_root).resolve()
        if not new.is_dir() or old==new:raise ValueError('请选择不同的有效新目录')
        plans=[];cancelled=getattr(progress,'cancelled',None)
        for row in self.db.execute('SELECT * FROM files').fetchall():
            check_cancelled(cancelled);f=dict(row)
            try:relative=Path(f['path']).resolve().relative_to(old)
            except ValueError:continue
            target=(new/relative).resolve()
            if not target.is_relative_to(new) or not target.is_file():raise ValueError('新目录缺少文件：'+str(relative))
            if progress:progress(len(plans),0,'校验 '+str(relative))
            cache=self.db.execute('SELECT full FROM import_cache WHERE file_id=?',(f['id'],)).fetchone()
            expected=(cache['full'] if cache else None) or f['digest']
            if expected.startswith('fast-'):
                if not Path(f['path']).is_file():raise ValueError('原视频离线且尚未完成指纹校验，无法安全重定位：'+str(relative))
                expected=fingerprint(f['path'],cancelled=cancelled)
            if fingerprint(target,cancelled=cancelled)!=expected:raise ValueError('文件校验不一致：'+str(relative))
            plans.append((str(target),str(new),expected,f['id']))
        if not plans:raise ValueError('原目录下没有媒体记录')
        def rewrite(value):
            if isinstance(value,dict):return {k:rewrite(v) for k,v in value.items()}
            if isinstance(value,list):return [rewrite(v) for v in value]
            if isinstance(value,str) and Path(value).is_absolute():
                try:return str(new/Path(value).relative_to(old))
                except ValueError:pass
            return value
        # Verify the complete plan before a single atomic update. Uniqueness failures roll back everything.
        with self.db:
            self.db.executemany('UPDATE files SET path=?,root=?,digest=? WHERE id=?',plans)
            self.db.executemany('DELETE FROM import_cache WHERE file_id=?',[(p[3],) for p in plans])
            ids={r[0] for r in self.db.execute('SELECT DISTINCT work_id FROM files WHERE root=?',(str(new),))}
            for identifier in ids:
                work=self.work(identifier)
                self.db.execute('UPDATE works SET metadata=?,thumbnail=? WHERE id=?',(json.dumps(rewrite(work['metadata']),ensure_ascii=False),rewrite(work['thumbnail']),identifier))
        return {'relocated':len(plans)}

    def edit_queue(self, ids, repeat=None):
        if not isinstance(ids,list) or len(ids)>10000 or any(type(i) is not int for i in ids):raise ValueError('无效队列')
        ids=list(dict.fromkeys(ids));valid={r[0] for r in self.db.execute('SELECT DISTINCT work_id FROM files')}
        if any(i not in valid for i in ids):raise ValueError('队列中包含不存在的本地影片')
        old=self.setting('queue',{'ids':[],'index':0})
        current=old['ids'][old['index']] if 0<=old['index']<len(old['ids']) else None
        mode=repeat if repeat is not None else old.get('repeat','off')
        if not isinstance(mode,str) or mode not in {'off','all','one'}:raise ValueError('无效循环模式')
        queue={**old,'ids':ids,'index':ids.index(current) if current in ids else 0,'repeat':mode}
        self.set_setting('queue',queue);return queue
