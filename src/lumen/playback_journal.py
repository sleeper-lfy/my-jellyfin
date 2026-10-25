"""Playback accounting snapshots: no SQLite writer waits on the GUI thread."""
from collections import Counter, OrderedDict
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from .core import Library, now


class PlaybackJournal:
    """Coalesce absolute totals and retry busy writers without double counting.

    The worker owns its SQLite connection. Samples keep their original timestamps
    on the UI thread, so delayed database access cannot count buffering or waiting
    for another task as watched time. Idle workers exit rather than accumulating
    one background thread for each temporary player window.
    """
    def __init__(self, directory):
        self.directory=directory
        self.condition=threading.Condition()
        self.pending=OrderedDict()
        self.latest_file={}
        self.sequence=0
        self.thread=None
        self.closed=False
        self.error=''
        self.shutdown_deadline=None
        self.recovery_path=Path(directory)/'playback-pending.json'
        self.recovery_loaded=False
        self.recovery_valid=True
        self.unsaved_error=''
        self._last_log=0

    def submit(self, key, value):
        with self.condition:
            if self.closed:raise RuntimeError('播放记录队列已关闭')
            self.sequence+=1
            sequence=self.sequence
            if key[0] in {'session','file_state'}:value={**value,'sampled':time.time_ns()}
            self.pending[key]=(sequence,value)
            if key[0] in {'session','file_state'}:self.latest_file[value['file_id']]=sequence
            self._start()
            self.condition.notify_all()

    def _start(self):
        if self.thread is None:
            self.thread=threading.Thread(target=self._run,name='PlaybackJournal',daemon=True)
            self.thread.start()

    def duration(self, file_id, seconds):
        self.submit(('duration',file_id),seconds)

    def completed(self, file_id):
        self.submit(('file_state',file_id),{'file_id':file_id,'completed':True,'position':0})

    def retry(self, *, keep_open=False):
        with self.condition:
            self.unsaved_error=''
            self.closed=not keep_open
            self.shutdown_deadline=None if keep_open else time.monotonic()+3
            if self.pending:self._start()
            self.condition.notify_all()

    def stop(self):
        """Request a final flush; callers poll without blocking the Qt event loop."""
        with self.condition:
            self.closed=True
            if self.shutdown_deadline is None:self.shutdown_deadline=time.monotonic()+3
            self.condition.notify_all()
            return self.thread is None

    def _load_recovery(self):
        if self.recovery_loaded:return
        self.recovery_loaded=True
        if not self.recovery_path.exists():return
        try:
            if self.recovery_path.stat().st_size>32*1024*1024:raise ValueError('播放恢复文件超过大小限制')
            records=json.loads(self.recovery_path.read_text(encoding='utf-8'))
            if not isinstance(records,list):raise ValueError('播放恢复文件格式错误')
            parsed=[]
            for entry in records:
                key,value=tuple(entry['key']),entry['value']
                if len(key)!=2 or key[0] not in {'session','duration','file_state'}:raise ValueError('播放恢复记录格式错误')
                if key[0]=='session' and (not isinstance(value,dict) or not {'file_id','started','ended','watched','days','position'}<=value.keys()):raise ValueError('播放恢复会话格式错误')
                parsed.append((key,value))
            with self.condition:
                for index,(key,value) in enumerate(parsed):
                    sequence=index-len(records)
                    self.pending.setdefault(key,(sequence,value))
                    if key[0] in {'session','file_state'} and self.latest_file.get(value['file_id'],0)<=0:
                        self.latest_file[value['file_id']]=sequence
            logging.info('Recovering %d pending playback records',len(records))
        except (OSError,ValueError,TypeError,KeyError):
            self.recovery_valid=False
            self.error='未能读取上次播放记录恢复文件；原文件已保留'
            logging.exception(self.error)

    def _preserve(self):
        """Atomic local recovery file if SQLite cannot flush within 3s of exit."""
        with self.condition:
            records=[{'key':list(key),'value':value} for key,(_,value) in sorted(self.pending.items(),key=lambda item:item[1][0])]
        temporary=self.recovery_path.with_suffix('.json.tmp')
        try:
            with temporary.open('w',encoding='utf-8') as stream:
                json.dump(records,stream,ensure_ascii=False)
                stream.flush();os.fsync(stream.fileno())
            if not self.recovery_valid and self.recovery_path.exists():
                self.recovery_path.replace(self.recovery_path.with_suffix('.invalid-'+uuid.uuid4().hex+'.json'))
            temporary.replace(self.recovery_path)
            logging.warning('Preserved %d playback records for next startup in %s',len(records),self.recovery_path)
            return True
        except OSError:
            self.unsaved_error='播放记录暂未保存：数据库与恢复文件均无法写入，请检查磁盘可用空间和权限'
            logging.exception(self.unsaved_error)
            return False

    def _write(self, library, key, sequence, value):
        with library.db:
            if key[0]=='duration':
                library.db.execute('UPDATE files SET duration=? WHERE id=?',(value,key[1]))
                return
            if key[0]=='file_state':
                state_key='playback-state:'+str(value['file_id'])
                stamp=value.get('sampled',0)
                if stamp>=library.setting(state_key,0):
                    library.db.execute('UPDATE files SET completed=? WHERE id=?',(value['completed'],value['file_id']))
                    library.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(state_key,json.dumps(stamp)))
                with self.condition:current=sequence==self.latest_file.get(value['file_id'])
                if current and self._newer_position(library,value):
                    library.db.execute('UPDATE files SET position=? WHERE id=?',(value['position'],value['file_id']))
                return
            if not library.db.execute('SELECT 1 FROM files WHERE id=?',(value['file_id'],)).fetchone():
                return  # The catalog entry was explicitly removed meanwhile.
            library.db.execute('INSERT INTO sessions(id,file_id,started,ended,watched) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ended=COALESCE(excluded.ended,sessions.ended),watched=MAX(sessions.watched,excluded.watched)',
                               (key[1],value['file_id'],value['started'],value['ended'],value['watched']))
            library.db.executemany('INSERT INTO activity(session_id,day,watched) VALUES (?,?,?) ON CONFLICT(session_id,day) DO UPDATE SET watched=MAX(activity.watched,excluded.watched)',
                                   [(key[1],day,watched) for day,watched in value['days'].items()])
            with self.condition:current=sequence==self.latest_file.get(value['file_id'])
            if current and value['position'] is not None and self._newer_position(library,value):
                library.db.execute('UPDATE files SET position=? WHERE id=?',(value['position'],value['file_id']))

    def _newer_position(self, library, value):
        # A crash can leave a recovery file whose earlier records already
        # reached SQLite. Keep a per-file stamp in the existing settings table
        # so replay cannot roll back a later pause/seek with equal watch totals.
        key='playback-position:'+str(value['file_id'])
        stamp=value.get('sampled',0)
        previous=library.setting(key,0)
        if stamp<previous:return False
        library.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(stamp)))
        return True

    def _run(self):
        library=None
        try:
            self._load_recovery()
            while True:
                with self.condition:
                    if not self.pending and not self.closed:self.condition.wait(.5)
                    idle=not self.pending
                    preserve=not idle and self.closed and self.shutdown_deadline is not None and time.monotonic()>=self.shutdown_deadline
                    if not idle and not preserve:key,(sequence,value)=self.pending.popitem(last=False)
                if idle:
                    # File I/O must never hold the lock needed by UI submissions
                    # or stop(). Recheck under the lock before retiring.
                    try:
                        if self.recovery_loaded and self.recovery_valid and not self.error:self.recovery_path.unlink(missing_ok=True)
                    except OSError:logging.exception('Could not remove flushed playback recovery file')
                    with self.condition:
                        if self.pending:continue
                        self.latest_file.clear()
                        self.thread=None
                    return
                if preserve:
                    if self._preserve():
                        with self.condition:self.pending.clear();self.latest_file.clear()
                    return
                try:
                    if library is None:library=Library(self.directory,initialize=False,timeout=.15)
                    self._write(library,key,sequence,value)
                    self.error=''
                    if key[0] in {'session','file_state'}:
                        with self.condition:
                            if sequence==self.latest_file.get(value['file_id']) and key not in self.pending:self.latest_file.pop(value['file_id'],None)
                except Exception as error:
                    self.error=str(error)
                    if time.monotonic()-self._last_log>=5:
                        logging.warning('Playback journal waiting to save: %s',error)
                        if not isinstance(error,(sqlite3.Error,OSError)):logging.exception('Unexpected playback journal failure')
                        self._last_log=time.monotonic()
                    with self.condition:
                        # Never replace a newer cumulative sample with an older
                        # failed write; the new sample includes its watched time.
                        self.pending.setdefault(key,(sequence,value))
                        self.condition.wait(.1)
        finally:
            if library:library.close()
            with self.condition:
                # A failed worker must not leave a stale thread reference that
                # prevents later samples or shutdown from retrying the queue.
                if self.thread is threading.current_thread():
                    self.thread=None
                    if self.pending and not self.unsaved_error:self._start()


class PlaybackSession:
    def __init__(self, journal, file_id, clock=time.monotonic):
        self.journal=journal
        self.file_id=file_id
        self.clock=clock
        self.id=uuid.uuid4().hex
        self.started=now()
        self.last_time=clock()
        self.last_position=None
        self.playing=False
        self.closed=False
        self.watched=0.0
        self.days=Counter()
        self._save()

    def _save(self):
        self.journal.submit(('session',self.id),{'file_id':self.file_id,'started':self.started,
                            'ended':now() if self.closed else None,'watched':self.watched,
                            'days':dict(self.days),'position':max(0,self.last_position) if self.last_position is not None else None})

    def tick(self, position, playing, rate=1.0, seeking=False):
        if self.closed:return
        current=self.clock()
        elapsed=current-self.last_time
        if self.playing and playing and not seeking and self.last_position is not None and 0<elapsed<=3:
            advance=position-self.last_position
            if 0<advance<=elapsed*rate+.6:
                watched=min(elapsed,advance/max(rate,.1))
                self.watched+=watched
                self.days[datetime.now().date().isoformat()]+=watched
        self.last_time,self.last_position,self.playing=current,position,playing
        self._save()

    def finish(self):
        if not self.closed:
            self.closed=True
            self._save()
