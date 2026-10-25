import json
import threading
import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from lumen.ui import MainWindow
from lumen.catalog_ui import StillViewer


def wait_for(predicate,seconds=4):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate()


def test_detail_cover_click_and_keyboard_open_single_image_without_changing_page(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'cover')
    with window.library.db:
        work_id=window.library.db.execute('INSERT INTO works(identity,kind,title,added,thumbnail,metadata) VALUES (?,?,?,?,?,?)',
            ('cover','movie','Cover','now',str(tmp_path/'poster.jpg'),json.dumps({}))).lastrowid
    opened=[]
    class Viewer:
        def __init__(self,paths,index=0,parent=None,title='剧照'):opened.append((paths,parent,title))
        def exec(self):return 0
        def deleteLater(self):pass
    monkeypatch.setattr('lumen.catalog_ui.StillViewer',Viewer)
    window.open_details(work_id,fetch=False);window.show();qapp.processEvents()
    page=window.detail_page
    QTest.mouseClick(page.poster,Qt.MouseButton.LeftButton)
    QTest.keyClick(page.poster,Qt.Key.Key_Return)
    assert len(opened)==2 and opened[0]==([str(tmp_path/'poster.jpg')],page,'封面')
    assert window.detail_page is page and window.pages.currentWidget() is window.details_scroll
    window.close()


def test_large_image_reads_keep_gui_responsive_and_only_newest_navigation_is_loaded(qapp,tmp_path,monkeypatch):
    from lumen import images
    entered=threading.Event();release=threading.Event();reads=[];gui_thread=threading.get_ident()
    def slow_decode(path,size):
        assert threading.get_ident()!=gui_thread
        reads.append(path)
        if path=='first':entered.set();release.wait(4)
        picture=QImage(60,90,QImage.Format.Format_RGB32);picture.fill(QColor('red' if path=='first' else 'green'));return picture
    monkeypatch.setattr(images,'decode',slow_decode)
    viewer=StillViewer(['first','skipped','latest'],title='封面')
    try:
        wait_for(entered.is_set)
        heartbeat=[];QTimer.singleShot(0,lambda:heartbeat.append(True))
        viewer.step(1);viewer.step(1)
        wait_for(lambda:bool(heartbeat))
        assert reads==['first'] and viewer.index==2
        release.set();wait_for(lambda:len(reads)==2 and bool(viewer.scene.items()))
        assert reads==['first','latest']
        image=viewer.scene.items()[0].pixmap().toImage()
        assert image.pixelColor(0,0).green()>100
        assert not viewer._active
    finally:release.set();viewer.close()


def test_actor_photo_entry_opens_with_current_actor_and_default_fill_policy(qapp,tmp_path):
    from lumen.actor_ui import show_actor_scraper
    from PySide6.QtWidgets import QLineEdit,QCheckBox
    window=MainWindow(tmp_path/'actors');dialog=show_actor_scraper(window,'Sample Actress')
    assert dialog.findChild(QLineEdit,'actorPhotoName').text()=='Sample Actress'
    assert not dialog.findChild(QCheckBox).isChecked()
    assert show_actor_scraper(window,'Other Actress') is dialog
    dialog.close();qapp.processEvents();window.close()
