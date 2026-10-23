"""Coalesced task history writes never wait for a SQLite writer on the GUI thread."""
import threading
from .core import Library
from .core import check_cancelled


class TaskBudget:
    def __init__(self,limit=1):
        self.condition=threading.Condition();self.limit=max(1,min(3,int(limit)));self.active=0;self.paused=False
    def set_limit(self,limit):
        with self.condition:self.limit=max(1,min(3,int(limit)));self.condition.notify_all()
    def acquire(self,cancelled=None):
        while True:
            check_cancelled(cancelled)
            with self.condition:
                if not self.paused and self.active<self.limit:self.active+=1;return
                self.condition.wait(.1)
    def set_paused(self,paused):
        with self.condition:self.paused=paused;self.condition.notify_all()
    def release(self):
        with self.condition:self.active-=1;self.condition.notify_all()


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
