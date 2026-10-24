"""Render real catalog UI with isolated synthetic sample metadata, never user media."""
import json
from pathlib import Path
import tempfile
import time
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage,QColor,QFont
from lumen.core import Library,identity,now
from lumen.ui import MainWindow
from lumen.theme import STYLE

app=QApplication([]);app.setStyleSheet(STYLE);app.setFont(QFont('Noto Sans CJK SC',10))
def settle(seconds=.2):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.processEvents();time.sleep(.01)
output=Path('docs/screenshots');output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='lumen-catalog-preview-') as folder:
    lib=Library(folder);poster=Path(folder)/'poster.jpg'
    image=QImage(400,600,QImage.Format.Format_RGB32);image.fill(QColor('#205064'));image.save(str(poster))
    for title,kind in [('山海纪行 · 示例剧集','series'),('森林之声 · 示例','movie'),('海岸来信 · 示例','movie')]:
        with lib.db:
            cur=lib.db.execute('INSERT INTO works(identity,kind,title,year,metadata,added,thumbnail) VALUES (?,?,?,?,?,?,?)',(identity(title,2024,kind),kind,title,2024,json.dumps({'overview':'独立示例资料库：展示季选择与观看管理，不含真实用户媒体。','tags':['纪录片']}),now(),str(poster)))
            wid=cur.lastrowid
            for season in ([1,2] if kind=='series' else [1]):
                for episode in ([1,2,3] if kind=='series' else [1]):
                    lib.db.execute('INSERT INTO files(work_id,path,digest,root,duration,season,episode) VALUES (?,?,?,?,?,?,?)',(wid,str(Path(folder)/f'{wid}.S{season:02}E{episode:02}.mp4'),f'{wid}-{season}-{episode}',folder,1500,season,episode))
    lib.edit_queue([1,2,3]);window=MainWindow(folder);window.resize(1280,900);window.show();window.open_details(1,fetch=False);settle(.3)
    window.detail_page.season_filter.setCurrentIndex(2);settle();window.grab().save(str(output/'catalog-season-pc.png'))
    window.back_details()
    def capture_queue():
        dialog=next(d for d in window.findChildren(QDialog) if d.windowTitle()=='播放队列 · 拖动排序' and d.isVisible())
        dialog.grab().save(str(output/'catalog-queue-pc.png'));dialog.reject()
    QTimer.singleShot(300,capture_queue);window.show_queue();window.close();lib.close()
