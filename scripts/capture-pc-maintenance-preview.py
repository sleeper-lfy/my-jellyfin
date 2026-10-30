"""Render actual controls with an isolated generated library; no installation or user media."""
from pathlib import Path
import json,tempfile,time
from PySide6.QtWidgets import QApplication,QTableWidget
from PySide6.QtGui import QImage,QPainter,QColor,QLinearGradient,QFont
from lumen.ui import MainWindow
from lumen.theme import STYLE

output=Path('docs/screenshots');output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setFont(QFont('Noto Sans CJK SC',10));app.setStyleSheet(STYLE)
def spin(seconds=.2):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:app.processEvents();time.sleep(.01)
def picture(path,width,height,title,color):
    image=QImage(width,height,QImage.Format.Format_RGB32);painter=QPainter(image)
    gradient=QLinearGradient(0,0,width,height);gradient.setColorAt(0,QColor(color));gradient.setColorAt(1,QColor('#101625'));painter.fillRect(image.rect(),gradient)
    painter.setPen(QColor('#cfe5ec'));painter.setFont(QFont('Noto Sans CJK SC',24));painter.drawText(32,height-40,title);painter.end();image.save(str(path))
with tempfile.TemporaryDirectory(prefix='lumen-maintenance-') as directory:
    root=Path(directory);media=root/'示例剧集';window=MainWindow(root/'data');window.resize(1280,900)
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    for title,color in [('旅途纪行','#27647c'),('城市切片','#705767')]:
        folder=media/title;folder.mkdir(parents=True)
        for index,name in enumerate(['[Studio] OVA 1 [DISC-001].mp4','未标编号的续篇.mp4']):(folder/name).write_bytes((title+str(index)).encode())
        picture(folder/'poster.jpg',320,480,title,color)
        (folder/'tvshow.nfo').write_text(f'<tvshow><title>{title}</title><plot>独立示例资料，用于预览按文件夹归集与剧照页面。</plot></tvshow>')
    window.library.import_folder(media,'series',fast=True);window.show();window.navigate('series');spin(.4)
    window.grab().save(str(output/'fix-series-folders-pc.png'))
    window.library.task('preview-import','import','done',{'title':'电视剧目录导入'},{'imported':4,'duplicates':0,'errors':[],'warnings':[]})
    window.library.task('preview-large','import','partial',{'title':'大报告预览示例'},{'errors':[{'path':'D:/示例目录/'+str(i)+'.mp4','reason':'示例诊断记录'} for i in range(12000)]})
    window.show_tasks();spin(.4);window.tasks_dialog.grab().save(str(output/'fix-tasks-pc.png'));window.tasks_dialog.close();spin()
    work=window.library.query()[0];shots=[]
    for index,(width,height) in enumerate([(960,540),(540,960)]):
        target=root/f'still-{index}.jpg';picture(target,width,height,f'剧照示例 {index+1}','#275a72');shots.append(str(target))
    metadata=work['metadata'];metadata['nfo_stills']=shots;metadata['nfo_backdrop']=shots[0]
    with window.library.db:window.library.db.execute('UPDATE works SET metadata=? WHERE id=?',(json.dumps(metadata),work['id']))
    window.open_details(work['id'],fetch=False);spin(.3)
    from lumen.catalog_ui import StillViewer
    viewer=StillViewer(shots,parent=window.detail_page);spin(.4)
    viewer.grab().save(str(output/'still-popup-pc.png'));viewer.close()
    updater=window.updater();updater.show();spin(.3);updater.dialog.grab().save(str(output/'fix-pc-updates.png'));updater.dialog.close()
    window.close();spin(.4)
