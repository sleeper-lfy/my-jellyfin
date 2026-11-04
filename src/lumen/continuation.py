"""Recently watched targets shared by desktop and the LAN client."""
from pathlib import Path


def resume_target(library, work, *, allow_completed=True):
    files = work['files']
    if not files:
        raise ValueError('该影片未入库')
    if work['kind'] != 'series':
        preferred = library.setting('preferred-file:' + str(work['id']))
        chosen = next((file for file in files if file['id'] == preferred), None)
        if chosen:
            available = Path(chosen['path']).is_file()
            if available and (not chosen['completed'] or (allow_completed and all(file['completed'] for file in files))):
                return chosen
            if not available:
                files = [file for file in files if file['id'] != chosen['id']] or files
    unfinished = [file for file in files if not file['completed']]
    if not unfinished:
        return files[0] if allow_completed else None
    marks = ','.join('?' for _ in files)
    recent = library.db.execute(f'''SELECT file_id,MAX(COALESCE(ended,started)) AS stamp
        FROM sessions WHERE file_id IN ({marks}) GROUP BY file_id ORDER BY stamp DESC,file_id DESC''',
        [file['id'] for file in files]).fetchall()
    partial = {file['id']: file for file in unfinished if file['position'] > 0}
    for row in recent:
        if row['file_id'] in partial:
            return partial[row['file_id']]
    if partial:
        return next(iter(partial.values()))
    if work['kind'] == 'series' and recent:
        last = next((index for index,file in enumerate(files) if file['id'] == recent[0]['file_id']), -1)
        following = next((file for file in files[last+1:] if not file['completed']), None)
        if following:return following
    return unfinished[0]


def describe(file, kind):
    position = max(0, float(file.get('position') or 0))
    duration = max(0, float(file.get('duration') or 0))
    if duration:position=min(position,duration)
    def clock(seconds):
        seconds=int(seconds)
        return f'{seconds//3600}:{seconds//60%60:02}:{seconds%60:02}' if seconds>=3600 else f'{seconds//60}:{seconds%60:02}'
    name = file.get('title') or Path(file['path']).name
    if kind == 'series' and file.get('season') is not None and file.get('episode') is not None:
        name=f"S{file['season']:02}E{file['episode']:02} · {name}"
    text=('继续 ' if position else '下一集 ' if kind=='series' else '播放 ')+name
    text+=' · '+clock(position)
    if duration:text+=' · 剩余 '+clock(max(0,duration-position))
    return {'file_id':file['id'],'name':name,'position':position,'duration':duration,
            'remaining':max(0,duration-position) if duration else None,'label':text}


def continue_works(library, limit=24):
    """Bound candidate IDs in SQL; fully watched works never return to this shelf."""
    limit=max(1,min(100,int(limit)))
    rows=library.db.execute('''SELECT w.id,
        COALESCE((SELECT MAX(COALESCE(s.ended,s.started)) FROM sessions s JOIN files sf ON sf.id=s.file_id WHERE sf.work_id=w.id),w.added) AS recent
        FROM works w WHERE EXISTS(SELECT 1 FROM files f WHERE f.work_id=w.id AND f.completed=0)
        AND (EXISTS(SELECT 1 FROM files f WHERE f.work_id=w.id AND f.completed=0 AND f.position>0)
             OR (w.kind='series' AND EXISTS(SELECT 1 FROM files f WHERE f.work_id=w.id AND f.completed=1)))
        ORDER BY recent DESC,w.id DESC LIMIT ?''',(limit,)).fetchall()
    result=[]
    for row in rows:
        work=library.work(row['id']);target=resume_target(library,work,allow_completed=False)
        if target is None:continue
        resume=describe(target,work['kind'])
        work['_resume']=resume;work['_subtitle']=resume['label'];work['_last_played']=row['recent']
        result.append(work)
    return result
