"""Desktop catalog management and fullscreen still viewer."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QListWidget,QListWidgetItem,QComboBox,QAbstractItemView,QMessageBox,QInputDialog,QFileDialog,QGraphicsView,QGraphicsScene)


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


class StillViewer(QDialog):
    def __init__(self, paths, index=0, parent=None):
        super().__init__(parent);self.paths=list(paths);self.index=index;self.setWindowTitle('剧照 · 滚轮缩放 / 左右切换 / Esc 关闭')
        layout=QVBoxLayout(self);self.view=QGraphicsView();self.scene=QGraphicsScene(self.view);self.view.setScene(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);layout.addWidget(self.view)
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('上一张',lambda:self.step(-1)),('下一张',lambda:self.step(1)),('放大',lambda:self.view.scale(1.25,1.25)),('缩小',lambda:self.view.scale(.8,.8)),('适应窗口',self.fit),('关闭',self.close)]:
            b=QPushButton(title);b.clicked.connect(callback);row.addWidget(b)
        for key,delta in [('Left',-1),('Right',1)]:QShortcut(QKeySequence(key),self,activated=lambda d=delta:self.step(d))
        self.view.wheelEvent=self.zoom;self.showFullScreen();self.load()
    def zoom(self,event):
        factor=1.2 if event.angleDelta().y()>0 else 1/1.2
        scale=self.view.transform().m11()
        if .02<scale*factor<30:self.view.scale(factor,factor)
        event.accept()
    def fit(self):self.view.fitInView(self.scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def load(self):
        self.scene.clear();self.view.resetTransform()
        if self.paths:
            reader=QImageReader(str(self.paths[self.index]));size=reader.size()
            if max(size.width(),size.height())>4096:reader.setScaledSize(size.scaled(4096,4096,Qt.AspectRatioMode.KeepAspectRatio))
            pixmap=QPixmap.fromImage(reader.read())
            if not pixmap.isNull():
                # Bound display memory independently of original still resolution.
                if max(pixmap.width(),pixmap.height())>4096:pixmap=pixmap.scaled(4096,4096,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                self.scene.addPixmap(pixmap);self.scene.setSceneRect(self.scene.itemsBoundingRect());self.fit()
    def step(self,delta):
        if self.paths:self.index=(self.index+delta)%len(self.paths);self.load()
