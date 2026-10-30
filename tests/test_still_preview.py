import json
import time
import pytest
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lumen.ui import MainWindow
from lumen.catalog_ui import StillViewer


@pytest.mark.parametrize('dismiss', ['click', 'escape'])
def test_click_opens_popup_navigates_and_restores_detail(qapp, tmp_path, dismiss, monkeypatch):
    paths=[]
    for index in range(2):
        path=tmp_path/f'{index}.png'
        image=QImage(800,450,QImage.Format.Format_RGB32);image.fill(QColor('red' if index==0 else 'green'));image.save(str(path));paths.append(str(path))
    window=MainWindow(tmp_path/'data');window.show()
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    with window.library.db:
        identifier=window.library.db.execute('INSERT INTO works(identity,kind,title,added,metadata) VALUES (?,?,?,?,?)',('popup','movie','Popup','now',json.dumps({'nfo_stills':paths}))).lastrowid
    window.open_details(identifier,fetch=False);qapp.processEvents();detail=window.detail_page
    scroll=window.details_scroll.verticalScrollBar().value();geometry=detail.size();errors=[];opened=[]
    def interact(viewer):
        try:
            assert isinstance(viewer,StillViewer);opened.append(viewer)
            assert viewer.index==1
            QTest.keyClick(viewer.view,Qt.Key.Key_Right);assert viewer.index==0
            QTest.keyClick(viewer.view,Qt.Key.Key_Left);assert viewer.index==1
            if dismiss=='click':QTest.mouseClick(viewer.view.viewport(),Qt.MouseButton.LeftButton)
            else:QTest.keyClick(viewer.view,Qt.Key.Key_Escape)
            assert not viewer.isVisible()
        except BaseException as error:errors.append(error)
        finally:
            if viewer:viewer.reject()
    try:
        def create_viewer(*args,**kwargs):
            viewer=StillViewer(*args,**kwargs)
            QTimer.singleShot(50,lambda:interact(viewer))
            return viewer
        monkeypatch.setattr('lumen.catalog_ui.StillViewer',create_viewer)
        detail.still_gallery.itemClicked.emit(detail.still_gallery.item(1))
        assert opened
        if errors:raise errors[0]
        assert not hasattr(detail,'expanded_still')
        assert detail.size()==geometry
        assert window.details_scroll.verticalScrollBar().value()==scroll
        assert window.detail_page is detail
    finally:
        window.close()
        deadline=time.monotonic()+5
        while window._auxiliary_jobs and time.monotonic()<deadline:QTest.qWait(10)


def test_dragging_picture_keeps_viewer_open(qapp,tmp_path):
    path=tmp_path/'still.png';image=QImage(1200,800,QImage.Format.Format_RGB32);image.fill(QColor('blue'));image.save(str(path))
    viewer=StillViewer([str(path)])
    try:
        deadline=time.monotonic()+3
        while not viewer.scene.items() and time.monotonic()<deadline:QTest.qWait(10)
        assert viewer.scene.items()
        viewer.view.scale(3,3)
        viewport=viewer.view.viewport();start=viewport.rect().center();end=start+QPoint(70,0)
        QTest.mousePress(viewport,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(viewport,end)
        QTest.mouseRelease(viewport,Qt.MouseButton.LeftButton,pos=end)
        assert viewer.isVisible()
        QTest.mouseClick(viewport,Qt.MouseButton.LeftButton,pos=end)
        assert not viewer.isVisible()
    finally:viewer.close()
