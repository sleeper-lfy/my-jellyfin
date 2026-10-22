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
    decoded=Signal(object,QImage)
    changed=Signal()
    def __init__(self,parent):
        super().__init__(parent);self.pool=QThreadPool(self);self.pool.setMaxThreadCount(2)
        self.cache=OrderedDict();self.pending=set();self.bytes=0;self.generation=0
        self.decoded.connect(self.loaded)
    def request(self,path,size):
        if not path:return QPixmap()
        key=(str(path),max(1,min(1400,size.width())),max(1,min(900,size.height())))
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        if key not in self.pending:
            self.pending.add(key);self.pool.start(Decode(self,key,self.generation))
        return QPixmap()
    @Slot(object,QImage)
    def loaded(self,ticket,image):
        generation,key=ticket
        if generation!=self.generation:return
        self.pending.discard(key);picture=QPixmap.fromImage(image)
        self.cache[key]=picture;self.bytes+=picture.width()*picture.height()*4
        while self.cache and (self.bytes>64*1024*1024 or len(self.cache)>512):
            _,old=self.cache.popitem(last=False);self.bytes-=old.width()*old.height()*4
        self.changed.emit()
    def invalidate(self):
        self.generation+=1;self.pool.clear();self.pending.clear();self.cache.clear();self.bytes=0
        self.changed.emit()


def image_cache():
    app=QApplication.instance()
    if not hasattr(app,'lumen_images'):app.lumen_images=ImageCache(app)
    return app.lumen_images
