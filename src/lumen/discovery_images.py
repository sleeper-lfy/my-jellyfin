"""Bounded downloads for the visible desktop discovery covers only."""
from collections import OrderedDict
import logging
import time
import weakref

from PySide6.QtCore import QObject,Signal,Slot,QEvent,QTimer,QRunnable,QThreadPool,Qt

from .core import Library
from .discovery_search import cache_discovery_cover


def visible_items(cards):
    """Enumerate a uniform wrapping grid without walking the whole loaded list."""
    if not cards.count():return []
    viewport=cards.viewport().rect()
    first=cards.visualItemRect(cards.item(0))
    if first.width()<=0 or first.height()<=0:return []
    columns=1
    limit=min(cards.count(),max(2,viewport.width()//first.width()+3))
    for index in range(1,limit):
        if cards.visualItemRect(cards.item(index)).top()!=first.top():break
        columns+=1
    pitch=first.height()+2*cards.spacing()
    if columns<cards.count():
        pitch=max(1,cards.visualItemRect(cards.item(columns)).top()-first.top())
    start=max(0,(-first.top())//pitch-1)*columns
    end=min(cards.count(),max(0,(viewport.bottom()-first.top())//pitch+2)*columns)
    return [cards.item(index) for index in range(start,end)
            if not cards.item(index).isHidden() and cards.visualItemRect(cards.item(index)).intersects(viewport)]


class CoverTask(QRunnable):
    def __init__(self,owner,directory,generation,work_id):
        super().__init__()
        self.owner,self.directory,self.generation,self.work_id=owner,directory,generation,work_id

    def run(self):
        library=None;path=''
        try:
            library=Library(self.directory,initialize=False,timeout=1)
            path=cache_discovery_cover(library,self.work_id) or ''
        except Exception as error:
            logging.info('Discovery cover %s could not be loaded: %s',self.work_id,error)
        finally:
            if library:library.close()
        self.owner.finished.emit(self.generation,self.work_id,path)


class DiscoveryImages(QObject):
    """Only IDs/tickets are queued; metadata and network I/O stay in workers."""
    max_pending=12
    max_workers=3
    finished=Signal(int,int,str)
    updated=Signal(int,str)

    def __init__(self,window):
        super().__init__(window)
        self.window=weakref.ref(window)
        self.cards=window.cards
        self.directory=window.library.directory
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(self.max_workers)
        self.pool.setExpiryTimeout(5000)
        self.generation=0
        self.view=None
        self.pending=set()
        self.active={}
        self.waiting=OrderedDict()
        self.failures=OrderedDict()
        self.stopped=False
        self.timer=QTimer(self);self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._refresh)
        self.finished.connect(self._loaded)
        self.cards.viewport().installEventFilter(self)

    @property
    def idle(self):return not self.active

    def _view(self):
        window=self.window()
        if (window is None or self.stopped or getattr(window,'_closing',False) or
            window.section!='discover' or not self.cards.isVisible() or not self.cards.isEnabled()):return None
        return (window.section,getattr(window,'_browse_epoch',0),getattr(window,'_rendered_view_key',None))

    def _sync_view(self):
        view=self._view()
        if view!=self.view:
            self.generation+=1
            self.view=view
            self.pending.difference_update(self.waiting)
            self.waiting.clear();self.failures.clear()
        return view is not None

    def refresh_visible(self,*_):
        # Invalidate immediately when the caller changes pages, before a queued
        # worker callback can touch cards belonging to the replacement page.
        if self._sync_view() and not self.timer.isActive():self.timer.start(0)

    def eventFilter(self,watched,event):
        if event.type() in {QEvent.Type.Show,QEvent.Type.Hide,QEvent.Type.Resize}:self.refresh_visible()
        return False

    def _candidates(self):
        result={}
        for item in visible_items(self.cards):
            data=item.data(Qt.ItemDataRole.UserRole) or {}
            work_id=data.get('id')
            if (type(work_id) is int and work_id>0 and data.get('kind') and
                not data.get('files') and not data.get('thumbnail') and not data.get('_cover')):
                result[work_id]=item
        return result

    def _refresh(self):
        if not self._sync_view():return
        candidates=self._candidates()
        for work_id in list(self.waiting):
            if work_id not in candidates:
                self.waiting.pop(work_id);self.pending.discard(work_id)
        now=time.monotonic()
        for work_id in candidates:
            if len(self.pending)>=self.max_pending:break
            if work_id in self.pending or now-self.failures.get(work_id,-1000)<30:continue
            self.pending.add(work_id);self.waiting[work_id]=self.generation
        while self.waiting and len(self.active)<self.max_workers:
            work_id,generation=self.waiting.popitem(last=False)
            self.active[work_id]=generation
            self.pool.start(CoverTask(self,self.directory,generation,work_id))

    @Slot(int,int,str)
    def _loaded(self,generation,work_id,path):
        self.active.pop(work_id,None);self.pending.discard(work_id)
        current=self._sync_view() and generation==self.generation
        if current and path:
            for item in visible_items(self.cards):
                data=item.data(Qt.ItemDataRole.UserRole) or {}
                if data.get('id')!=work_id or data.get('files') or data.get('thumbnail'):continue
                item.setData(Qt.ItemDataRole.UserRole,{**data,'thumbnail':path,'_cover':path})
                self.cards.viewport().update(self.cards.visualItemRect(item))
            # This list already belongs to the window; retain no copy in the
            # controller and keep its next incremental paint on the same cover.
            window=self.window()
            if window is not None:
                for record in getattr(window,'current_items',[]):
                    if record.get('id')==work_id and not record.get('files'):
                        record['thumbnail']=path
                        break
            self.updated.emit(work_id,path)
        elif current:
            self.failures[work_id]=time.monotonic()
            while len(self.failures)>128:self.failures.popitem(last=False)
        self.refresh_visible()

    def stop(self):
        self.stopped=True;self.generation+=1;self.timer.stop()
        self.pending.difference_update(self.waiting)
        self.waiting.clear();self.failures.clear()

    def resume(self):
        self.stopped=False;self.view=None
        self.refresh_visible()
