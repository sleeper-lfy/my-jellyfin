"""Capture real PC controls using an isolated synthetic catalog; never moves user media."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
from pathlib import Path
from PySide6.QtGui import QColor,QFont,QImage,QLinearGradient,QPainter
from PySide6.QtWidgets import QApplication,QScrollArea
from lumen.ui import MainWindow
from lumen.theme import STYLE
from lumen import media_libraries as libraries
from lumen.media_libraries_ui import MediaLibraryDialog
from lumen.media_management_ui import MediaManagement

output=Path('docs/screenshots/media-libraries');output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setFont(QFont('Noto Sans CJK SC',10));app.setStyleSheet(STYLE)
MainWindow.synchronous_small_catalog=True


def spin():
    until=time.monotonic()+.3
    while time.monotonic()<until:app.processEvents();time.sleep(.01)


def artwork(path,title,color):
    image=QImage(600,900,QImage.Format.Format_RGB32);painter=QPainter(image)
    gradient=QLinearGradient(0,0,600,900);gradient.setColorAt(0,QColor(color));gradient.setColorAt(1,QColor('#101625'))
    painter.fillRect(image.rect(),gradient);painter.setPen(QColor('#e2edf3'));painter.setFont(QFont('Noto Sans CJK SC',32))
    painter.drawText(40,780,title);painter.end();image.save(str(path))


with tempfile.TemporaryDirectory(prefix='lumen-library-preview-') as directory:
    root=Path(directory);window=MainWindow(root/'data');window.resize(1280,900)
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    folders=[root/name for name in ['电影硬盘01','电影硬盘02','全景旅行']]
    for folder in folders:folder.mkdir()
    family=libraries.save(window.library,'家庭电影','movie',{'watch':False,'roots':[{'path':str(folder)} for folder in folders[:2]]})
    libraries.save(window.library,'VR 旅行','vr',{'watch':False,'roots':[{'path':str(folders[2])}]})
    libraries.save(window.library,'追剧清单','series',{'watch':False,'roots':[]})
    for folder,title,color,kind in zip(folders,['山海纪行','城市回声','云端之旅'],['#2e6877','#6d526b','#375d8a'],['movie','movie','vr']):
        (folder/(title+'.mp4')).write_bytes(title.encode());artwork(folder/'poster.jpg',title,color)
        (folder/(title+'.nfo')).write_text('<movie><title>'+title+'</title><year>2024</year></movie>',encoding='utf-8')
        window.library.import_folder(folder,kind,fast=True)
    window.refresh_media_libraries();window.show();window.navigate('home');spin()
    window.grab().save(str(output/'pc-home.png'))
    window.open_media_library(family['id']);spin();window.grab().save(str(output/'pc-library.png'))
    manager=MediaManagement(window);manager.select('libraries');manager.media_libraries.reload(family['id']);manager.show();spin()
    manager.grab().save(str(output/'pc-manager.png'));manager.close();spin()
    editor=MediaLibraryDialog(window,family);editor.resize(860,880);editor.show();spin()
    editor.grab().save(str(output/'pc-config.png'))
    scroll=editor.findChild(QScrollArea);scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum());spin()
    editor.grab().save(str(output/'pc-config-rules.png'));editor.reject();window.close();spin()
