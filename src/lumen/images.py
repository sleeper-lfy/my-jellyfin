"""Bounded background image decoding. QPixmap creation remains on the GUI thread."""
from collections import OrderedDict
from PySide6.QtCore import QObject,Signal,Slot,QSize,QRunnable,QThreadPool,Qt
from PySide6.QtGui import QImage,QImageReader,QPixmap
from PySide6.QtWidgets import QApplication


def decode(path,size):
    reader=QImageReader(path);reader.setAutoTransform(True);original=reader.size()
    if original.width()<=0 or original.height()<=0 or original.width()*original.height()>40_000_000:return QImage()
    target=original.scaled(size,Qt.AspectRatioMode.KeepAspectRatio)
    if target.width()<original.width() or target.height()<original.height():reader.setScaledSize(target)
    return reader.read()


class Decode(QRunnable):
    def __init__(self,loader,key,generation):super().__init__();self.loader=loader;self.key=key;self.generation=generation
    def run(self):
        try:picture=decode(self.key[0],QSize(self.key[1],self.key[2]))
        except Exception:picture=QImage()
        self.loader.decoded.emit((self.generation,self.key),picture)


class ImageCache(QObject):
    max_bytes=32*1024*1024
    max_entries=256
    max_pending=32
    decoded=Signal(object,QImage)
    changed=Signal()
    def __init__(self,parent):
        super().__init__(parent);self.pool=QThreadPool(self);self.pool.setMaxThreadCount(2)
        self.cache=OrderedDict();self.pending=set();self.waiting=OrderedDict();self.active=0;self.stale=set();self.bytes=0;self.generation=0
        self.decoded.connect(self.loaded)
    def request(self,path,size):
        if not path:return QPixmap()
        key=(str(path),max(1,min(1400,((size.width()+63)//64)*64)),max(1,min(900,((size.height()+63)//64)*64)))
        if key in self.cache and key not in self.stale:
            self.cache.move_to_end(key);return self.cache[key]
        if key not in self.pending and len(self.pending)<self.max_pending:
            self.pending.add(key);self.waiting[key]=self.generation;self.start_next()
        if key in self.cache:self.cache.move_to_end(key);return self.cache[key]
        return QPixmap()
    @Slot(object,QImage)
    def loaded(self,ticket,image):
        generation,key=ticket
        self.active-=1
        if generation!=self.generation:self.start_next();return
        self.pending.discard(key);self.stale.discard(key);picture=QPixmap.fromImage(image)
        previous=self.cache.pop(key,None)
        if previous is not None:self.bytes-=previous.width()*previous.height()*4
        self.cache[key]=picture;self.bytes+=picture.width()*picture.height()*4
        while self.cache and (self.bytes>self.max_bytes or len(self.cache)>self.max_entries):
            old_key,old=self.cache.popitem(last=False);self.stale.discard(old_key);self.bytes-=old.width()*old.height()*4
        self.start_next();self.changed.emit()
    def start_next(self):
        # Do not let workers outrun GUI delivery and queue many decoded QImages.
        while self.active<2 and self.waiting:
            key,generation=self.waiting.popitem(last=False);self.active+=1;self.pool.start(Decode(self,key,generation))
    def invalidate(self):
        # Keep the previous decoded picture until its replacement is ready.
        self.generation+=1;self.waiting.clear();self.pending.clear();self.stale=set(self.cache)
        self.changed.emit()


def image_cache():
    app=QApplication.instance()
    if not hasattr(app,'lumen_images'):app.lumen_images=ImageCache(app)
    return app.lumen_images
