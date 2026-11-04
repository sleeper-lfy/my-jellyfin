"""Coalesced task history writes never wait for a SQLite writer on the GUI thread."""
import threading
from .core import Library
from .core import check_cancelled


class TaskBudget:
    """Shared concurrency, resource lanes and cooperative playback yielding.

    A worker owns one lease per thread. Checkpoints release a background lease
    before waiting, so a user operation can use the freed capacity immediately.
    """
    def __init__(self,limit=1):
        self.condition=threading.Condition();self.limit=max(1,min(3,int(limit)))
        self.active=0;self.paused=False;self.playback=False
        self.leases={};self.waiters=[];self.resources={}
    def set_limit(self,limit):
        with self.condition:self.limit=max(1,min(3,int(limit)));self.condition.notify_all()
    def set_playback(self,playing):
        with self.condition:self.playback=bool(playing);self.condition.notify_all()
    def acquire(self,cancelled=None,*,resource=None,background=False):
        if resource not in (None,'disk','cpu','network'):raise ValueError('未知后台资源类型')
        ticket=object();waiter=(ticket,background,resource)
        with self.condition:self.waiters.append(waiter)
        try:
            while True:
                check_cancelled(cancelled)
                with self.condition:
                    eligible=[w for w in self.waiters if not (w[1] and self.playback)
                              and (w[2] is None or self.resources.get(w[2],0)<(2 if w[2]=='network' else 1))]
                    first=min(eligible,key=lambda w:w[1]) if eligible else None
                    if not self.paused and self.active<self.limit and first is waiter:
                        self.active+=1;self.resources[resource]=self.resources.get(resource,0)+1
                        self.leases[threading.get_ident()]=(resource,background)
                        return
                    self.condition.wait(.1)
        finally:
            with self.condition:self.waiters.remove(waiter);self.condition.notify_all()
    def checkpoint(self,cancelled=None):
        with self.condition:
            lease=self.leases.get(threading.get_ident())
            yield_now=lease and (self.paused or lease[1] and self.playback)
        if yield_now:
            self.release()
            self.acquire(cancelled,resource=lease[0],background=lease[1])
    def set_paused(self,paused):
        with self.condition:self.paused=paused;self.condition.notify_all()
    def release(self):
        with self.condition:
            lease=self.leases.pop(threading.get_ident(),None)
            if lease is not None:
                self.active-=1;self.resources[lease[0]]-=1
            self.condition.notify_all()


class TaskJournal:
    def __init__(self,directory):
        self.directory=directory;self.pending={};self.condition=threading.Condition();self.closed=False
        self.thread=threading.Thread(target=self.run,name='TaskJournal',daemon=True);self.thread.start()
    def record(self,identifier,kind,status,payload,result=None,error=None):
        with self.condition:
            if self.closed:return
            self.pending[identifier]=(identifier,kind,status,payload,result,error);self.condition.notify()
    def run(self):
        library=Library(self.directory,initialize=False)
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda:self.pending or self.closed)
                    if not self.pending:return
                    identifier=next(iter(self.pending));entry=self.pending.pop(identifier)
                try:library.task(*entry)
                except Exception:
                    # Original operations have their own durable task records.
                    # A history write must not terminate the GUI or its worker.
                    pass
        finally:library.close()
    def stop(self):
        with self.condition:self.closed=True;self.condition.notify_all()
        self.thread.join(timeout=1)
