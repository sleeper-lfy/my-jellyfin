import json
import time
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtGui import QPixmap,QColor
from lumen import images
from lumen.ui import MainWindow


def spin(app,seconds=.03):
    loop=QEventLoop();QTimer.singleShot(round(seconds*1000),loop.quit);loop.exec();app.processEvents()


def test_switching_stills_keeps_geometry_and_previous_image_until_decode_finishes(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'gallery');window.show()
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    with window.library.db:
        identifier=window.library.db.execute('INSERT INTO works(identity,kind,title,added,metadata) VALUES (?,?,?,?,?)',('preview','movie','Preview','now',json.dumps({'nfo_stills':['one','two']}))).lastrowid
    red=QPixmap(800,450);red.fill(QColor('red'));green=QPixmap(450,800);green.fill(QColor('green'));ready=[False]
    cache=images.image_cache()
    def request(path,size):
        if path=='one':return red
        if path=='two' and ready[0]:return green
        return QPixmap()
    monkeypatch.setattr(cache,'request',request)
    try:
        window.open_details(identifier);spin(qapp);detail=window.detail_page
        detail.show_still(detail.still_gallery.item(0));spin(qapp)
        size=detail.expanded_still.size();old=detail.expanded_still.pixmap().cacheKey();scroll=window.details_scroll.verticalScrollBar().value()
        detail.show_still(detail.still_gallery.item(1));spin(qapp)
        assert detail.expanded_still.size()==size and detail.expanded_still.pixmap().cacheKey()==old
        assert window.details_scroll.verticalScrollBar().value()==scroll
        ready[0]=True;detail.render_artwork();spin(qapp)
        assert detail.expanded_still.size()==size and detail.expanded_still.pixmap().toImage().pixelColor(0,0).green()>100
        current=detail.expanded_still.pixmap().cacheKey();detail.show_still(detail.still_gallery.item(1));spin(qapp)
        assert detail.expanded_still.pixmap().cacheKey()==current and window.details_scroll.verticalScrollBar().value()==scroll
    finally:
        window.close()
        deadline=time.monotonic()+8
        while (window.jobs or window._auxiliary_jobs or window.isVisible()) and time.monotonic()<deadline:spin(qapp)
