"""Capture actual Qt pages using a temporary, clearly marked demonstration library."""
import argparse,json,tempfile,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QLinearGradient
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from lumen.core import Library,identity,now
from lumen.ui import MainWindow,FilterDialog
from lumen.theme import STYLE


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/screenshots');args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setStyleSheet(STYLE);app.setFont(QFont('Noto Sans CJK SC',10))
    window=None
    def settle(seconds=.25):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        deadline=time.monotonic()+10
        while window is not None and (window._browse_job is not None or window._browse_pending is not None):
            if time.monotonic()>deadline:raise RuntimeError('Screenshot capture timed out waiting for catalog')
            app.processEvents();time.sleep(.01)
        app.processEvents()
    with tempfile.TemporaryDirectory(prefix='lumen-ui-preview-') as temporary:
        library=Library(Path(temporary)/'library')
        titles=['海岸纪行','森林之声','城市之夜','雪山之巅','远方灯塔','群星之间','荒野来信','夏日回声','山海之间','暮色航线','风的方向','大地之歌']
        colors=['#187a98','#386c5b','#555181','#637c94','#467580','#535e8c']
        for index,title in enumerate(titles):
            cover=library.directory/'cache'/f'preview-{index}.jpg'
            image=QImage(400,600,QImage.Format.Format_RGB32);painter=QPainter(image)
            gradient=QLinearGradient(0,0,400,600);gradient.setColorAt(0,QColor(colors[index%len(colors)]));gradient.setColorAt(1,QColor('#10151f'));painter.fillRect(image.rect(),gradient)
            painter.setPen(QColor('#c5dee3'));painter.drawEllipse(240,72,76,76)
            painter.drawLine(35,370,180,240);painter.drawLine(180,240,330,370);painter.drawLine(5,405,290,290);painter.drawLine(290,290,410,405)
            painter.setFont(QFont('Noto Sans CJK SC',25));painter.drawText(image.rect().adjusted(24,275,-24,-100),Qt.AlignmentFlag.AlignCenter,title)
            painter.setFont(QFont('Noto Sans CJK SC',10));painter.drawText(image.rect().adjusted(24,490,-24,-25),Qt.AlignmentFlag.AlignCenter,'LUMEN · 界面预览');painter.end();image.save(str(cover))
            metadata={'tags':['纪录片','旅行'],'actors':[{'name':'林遥','gender':'female'},{'name':'周宁','gender':'female'}],
                      'overview':'沿着海岸线向北，穿过清晨的港口与安静的山林。这是一段关于风景、相遇与日常的旅程。\n本页面使用独立测试库，封面、评分和观看状态均为界面演示数据。'}
            with library.db:
                work_id=library.db.execute('INSERT INTO works(identity,kind,title,year,metadata,thumbnail,added,favorite,watchlist,rating) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (identity(title,2024,'movie'),'movie',title,2024,json.dumps(metadata,ensure_ascii=False),str(cover),now(),int(index%3==0),int(index%4==1),8 if index==0 else None)).lastrowid
                library.db.execute('INSERT INTO files(work_id,path,digest,root,duration,position) VALUES (?,?,?,?,?,?)',
                    (work_id,str(Path(temporary)/(title+'.mp4')),f'preview-{index}',temporary,5600,1600 if index==0 else 0))
                library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',(work_id,'local-nfo','本地 NFO',str(index),'',now(),None,8.1+index%6*.1))
        backdrop=library.directory/'cache'/'landscape.jpg';image=QImage(1200,675,QImage.Format.Format_RGB32);painter=QPainter(image)
        gradient=QLinearGradient(0,0,0,675);gradient.setColorAt(0,QColor('#486b7d'));gradient.setColorAt(.6,QColor('#244655'));gradient.setColorAt(1,QColor('#132735'));painter.fillRect(image.rect(),gradient)
        painter.setPen(QColor('#b9d4db'));painter.drawEllipse(875,75,80,80)
        painter.drawLine(0,500,350,200);painter.drawLine(350,200,800,590);painter.drawLine(500,520,800,310);painter.drawLine(800,310,1200,590);painter.end();image.save(str(backdrop))
        with library.db:
            work=library.work(1);metadata=work['metadata'];metadata.update(nfo_backdrop=str(backdrop),nfo_stills=[str(backdrop)])
            library.db.execute('UPDATE works SET metadata=? WHERE id=1',(json.dumps(metadata,ensure_ascii=False),))
        window=MainWindow(library.directory);window.resize(1280,900);window.show();window.navigate('movie');settle(.5)
        QTest.mouseMove(window.cards.viewport(),window.cards.visualItemRect(window.cards.item(0)).center());settle()
        window.grab().save(str(output/'ui-library.png'))
        window.filters={'tags_all':['纪录片'],'actor':'林遥','year_min':2020,'year_max':2025};window.refresh();settle()
        window.grab().save(str(output/'ui-filter-results.png'))
        filters=FilterDialog(window.effective_filters(),window,library.filter_options());filters.show();settle();filters.grab().save(str(output/'ui-filters.png'));filters.reject();settle()
        window.open_details(1,fetch=False);settle(.5);window.grab().save(str(output/'ui-detail.png'))
        window.resize(1024,700);settle();window.grab().save(str(output/'ui-detail-compact.png'))
        from lumen.catalog_ui import StillViewer
        viewer=StillViewer([library.work(1)['thumbnail']],parent=window,title='封面')
        deadline=time.monotonic()+10
        while not viewer.scene.items() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        if not viewer.scene.items():raise RuntimeError('Screenshot capture timed out waiting for cover')
        settle();viewer.grab().save(str(output/'ui-cover-fullscreen.png'));viewer.close();viewer.deleteLater()
        window.close();settle();library.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
