"""Desktop catalog management and fullscreen still viewer."""
from pathlib import Path
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QSize
from PySide6.QtGui import QImage,QPixmap,QShortcut,QKeySequence
from PySide6.QtWidgets import (QApplication,QLabel,QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QListWidget,QListWidgetItem,QComboBox,QAbstractItemView,QMessageBox,QInputDialog,QFileDialog,QGraphicsView,QGraphicsScene)


def queue_editor(window):
    dialog=QDialog(window);dialog.setWindowTitle('播放队列 · 拖动排序');dialog.resize(620,540)
    layout=QVBoxLayout(dialog);items=QListWidget();items.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    queue=window.library.setting('queue',{'ids':[],'index':0})
    for i in queue['ids']:
        try:work=window.library.work(i)
        except ValueError:continue
        item=QListWidgetItem(work['title']);item.setData(Qt.ItemDataRole.UserRole,i);items.addItem(item)
    items.setCurrentRow(queue.get('index',0));layout.addWidget(items);repeat=QComboBox()
    for title,key in [('播完停止','off'),('列表循环','all'),('单部循环','one')]:repeat.addItem(title,key)
    repeat.setCurrentIndex(max(0,repeat.findData(queue.get('repeat','off'))));layout.addWidget(repeat)
    row=QHBoxLayout();layout.addLayout(row)
    remove=QPushButton('移除所选');remove.clicked.connect(lambda:items.takeItem(items.currentRow()) if items.currentRow()>=0 else None);row.addWidget(remove)
    def save(play=False):
        q=window.library.edit_queue([items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(items.count())],repeat.currentData())
        if play and items.currentRow()>=0:
            q['index']=items.currentRow();window.library.set_setting('queue',q);window.queue_play(0)
        dialog.accept()
    for title,callback in [('保存',lambda:save()),('播放所选',lambda:save(True))]:
        b=QPushButton(title);b.clicked.connect(callback);row.addWidget(b)
    controls=QHBoxLayout();layout.addLayout(controls)
    for title,delta in [('上一作品',-1),('继续队列',0),('下一作品',1)]:
        b=QPushButton(title);b.clicked.connect(lambda checked=False,d=delta:window.queue_play(d));controls.addWidget(b)
    def reshuffle():
        from .ui import FilterDialog
        f=FilterDialog(queue.get('filters',{}),dialog,window.library.filter_options())
        if f.exec() and f.filters()['kinds']:window.shuffle(f.filters());dialog.accept()
    b=QPushButton('设置全局范围 / 重新洗牌');b.clicked.connect(reshuffle);layout.addWidget(b)
    dialog.exec()


def batch_menu(window):
    from PySide6.QtWidgets import QMenu
    ids=[i.data(Qt.ItemDataRole.UserRole)['id'] for i in window.cards.selectedItems() if i.data(Qt.ItemDataRole.UserRole).get('kind')]
    if not ids:QMessageBox.information(window,'批量操作','先点击“多选”，再选择作品。');return
    menu=QMenu(window)
    def apply(action,value=None):
        try:window.library.batch_catalog(ids,action,value);window.refresh()
        except Exception as e:QMessageBox.warning(window,'未完成',str(e))
    for title,action,value in [('收藏','favorite',True),('取消收藏','favorite',False),('想看','watchlist',True),('标记已看','completed',None),('标记未看 / 重置进度','unwatched',None)]:
        menu.addAction(title,lambda checked=False,a=action,v=value:apply(a,v))
    def tags():
        text,ok=QInputDialog.getText(window,'批量追加标签','标签（逗号分隔；保留原标签）')
        if ok:apply('tags',[v.strip() for v in text.replace('，',',').split(',') if v.strip()])
    menu.addAction('追加标签…',tags);menu.exec(window.cursor().pos())


def relocate(window):
    old=QFileDialog.getExistingDirectory(window,'选择原目录（已离线可取消后输入路径）')
    if not old:old,ok=QInputDialog.getText(window,'原目录','输入媒体库记录中的原目录路径');
    if not old:return
    new=QFileDialog.getExistingDirectory(window,'选择新媒体目录')
    if not new:return
    window.run_job('校验并重定位媒体',lambda lib,progress:lib.relocate_root(old,new,progress))


class _PictureResult(QObject):
    loaded=Signal(int,QImage)


class _PictureRead(QRunnable):
    def __init__(self,result,ticket,path):
        super().__init__();self.result=result;self.ticket=ticket;self.path=path

    def run(self):
        from .images import decode
        try:picture=decode(str(self.path),QSize(4096,4096))
        except Exception:picture=QImage()
        self.result.loaded.emit(self.ticket,picture)


class StillViewer(QDialog):
    def __init__(self, paths, index=0, parent=None,title='剧照'):
        super().__init__(parent);self.paths=list(paths);self.index=max(0,min(index,len(self.paths)-1));self.setWindowTitle(title+' · 滚轮缩放 / 拖动查看 / Esc 关闭')
        self._ticket=0;self._active=False;self._pending=None;self._closed=False
        self.result=_PictureResult();self.result.loaded.connect(self.picture_loaded)
        app=QApplication.instance()
        if not hasattr(app,'lumen_gallery_pool'):
            app.lumen_gallery_pool=QThreadPool(app);app.lumen_gallery_pool.setMaxThreadCount(1)
        self.pool=app.lumen_gallery_pool
        layout=QVBoxLayout(self);self.view=QGraphicsView();self.scene=QGraphicsScene(self.view);self.view.setScene(self.scene)
        self.view.setStyleSheet('QGraphicsView { background: #080808; border: none; }')
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);layout.addWidget(self.view)
        self.status=QLabel();self.status.setFixedHeight(28);layout.addWidget(self.status)
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('上一张',lambda:self.step(-1)),('下一张',lambda:self.step(1)),('放大',lambda:self.view.scale(1.25,1.25)),('缩小',lambda:self.view.scale(.8,.8)),('适应窗口',self.fit),('关闭',self.close)]:
            b=QPushButton(title);b.clicked.connect(callback);row.addWidget(b)
            if title in ('上一张','下一张'):b.setEnabled(len(self.paths)>1)
        for key,delta in [('Left',-1),('Right',1)]:QShortcut(QKeySequence(key),self,activated=lambda d=delta:self.step(d))
        self.view.wheelEvent=self.zoom;self.showFullScreen();self.load()
    def zoom(self,event):
        factor=1.2 if event.angleDelta().y()>0 else 1/1.2
        scale=self.view.transform().m11()
        if .02<scale*factor<30:self.view.scale(factor,factor)
        event.accept()
    def fit(self):self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def load(self):
        self._ticket+=1
        if not self.paths:return
        self.status.setText(f'{self.index+1} / {len(self.paths)} · 正在加载图片…')
        # Coalesce rapid navigation: only the active read and newest request survive.
        self._pending=(self._ticket,self.paths[self.index]);self.start_read()

    def start_read(self):
        if self._active or self._pending is None or self._closed:return
        ticket,path=self._pending;self._pending=None;self._active=True
        self.pool.start(_PictureRead(self.result,ticket,path))

    def picture_loaded(self,ticket,picture):
        self._active=False
        if self._closed:return
        if ticket==self._ticket:
            if picture.isNull():self.status.setText('图片无法读取，可关闭后重新选择；原始文件不会修改。')
            else:
                self.scene.clear();self.view.resetTransform()
                self.scene.addPixmap(QPixmap.fromImage(picture));self.scene.setSceneRect(self.scene.itemsBoundingRect());self.fit()
                self.status.setText(f'{self.index+1} / {len(self.paths)} · 滚轮缩放 / 拖动查看 / Esc 关闭')
        self.start_read()

    def done(self,result):
        self._closed=True;self._pending=None
        super().done(result)
    def step(self,delta):
        if self.paths:self.index=(self.index+delta)%len(self.paths);self.load()
