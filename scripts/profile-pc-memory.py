"""Linux UI-only memory probe with isolated generated posters and synthetic catalog records.

Run with QT_QPA_PLATFORM=offscreen. Prints RSS after six identical navigation /
scroll / refresh cycles; creates no user media, watch sessions or persistent library.
"""
from pathlib import Path
import gc,json,tempfile,time
from PySide6.QtWidgets import QApplication,QListWidget
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import QEventLoop,QTimer
from lumen.ui import MainWindow
from lumen.images import image_cache
app=QApplication([])
def spin(ms=30):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec();app.processEvents()
def rss():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])*1024
with tempfile.TemporaryDirectory(prefix='lumen-memory-') as directory:
    root=Path(directory);media=root/'fixture';media.mkdir();window=MainWindow(root/'data');window.resize(1280,900)
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    posters=[]
    for index in range(90):
        path=media/f'{index}.jpg';image=QImage(1000,1500,QImage.Format.Format_RGB32);image.fill(QColor.fromHsv(index*3,180,160));image.save(str(path));posters.append(path)
    with window.library.db:
        for index,path in enumerate(posters):
            metadata=json.dumps({'overview':'Example plot '*400,'tags':['Fixture'],'stills':[str(path)]*20})
            cur=window.library.db.execute('INSERT INTO works(identity,kind,title,added,metadata,thumbnail) VALUES (?,?,?,?,?,?)',(f'memory:{index}','movie',f'Fixture {index}','2026-01-01',metadata,str(path)))
            window.library.db.execute('INSERT INTO files(work_id,path,root,digest,duration) VALUES (?,?,?,?,?)',(cur.lastrowid,str(media/f'{index}.mp4'),str(media),f'fixture-{index}',600))
    window.show();window.navigate('movie');spin(200);samples=[];widgets=[]
    for cycle in range(6):
        for section in ['home','movie']:
            window.navigate(section);spin(80)
            if section=='movie':
                while window.display_count<len(window.current_items):window.append_cards()
                bar=window.cards.verticalScrollBar()
            else:bar=window.home_page.verticalScrollBar()
            for position in range(0,bar.maximum()+1,600):bar.setValue(position);spin(35)
            for repeat in range(5):window.refresh();spin(30)
        gc.collect();spin(60);samples.append(rss());widgets.append(len(window.findChildren(QListWidget)))
    print(json.dumps({'rss_bytes':samples,'list_widgets':widgets,'image_bytes':image_cache().bytes,'image_entries':len(image_cache().cache),'pending':len(image_cache().pending)}),flush=True)
    window.close();spin()
