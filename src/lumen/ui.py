from __future__ import annotations
import json
import os
from html import escape
from pathlib import Path
import time
import threading
import uuid
from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer, QUrl, QRect, QPoint
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtGui import QPixmap, QIcon, QColor, QPainter, QFont, QDesktopServices, QPixmapCache, QLinearGradient, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
 QBoxLayout, QGridLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
 QMessageBox, QInputDialog, QListWidget, QListWidgetItem, QAbstractItemView, QTreeWidget,
 QTreeWidgetItem, QSplitter, QTabBar, QScrollArea, QPlainTextEdit, QTableWidget, QTableWidgetItem,
 QHeaderView, QStackedWidget, QProgressBar, QStyledItemDelegate, QStyle, QMenu, QCompleter, QSizePolicy)
from .core import Library, thumbnail, tool, set_tool_directory, ImportCancelled, check_cancelled
from .plugins import Plugins
from .files import plan_move, execute_move
from .player import Player
from .presentation import rating_text
from .theme import STYLE
from .components import ActionButton,FlowLayout,chip,icon,ElidedLabel

KINDS = {'movie': '电影', 'series': '电视剧', 'vr': 'VR电影', 'fans': 'Fans', 'other': '其他'}
FFTOOLS_JOB = 'fftools-download'
INSPECT_JOB = 'library-inspection'


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName('primary')
    return widget


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


def update_poster_items(cards,records,preserve=True):
    """Reconcile existing rows without a blank model or lost scroll/selection."""
    def key(record):return ('work',record['id']) if 'id' in record else ('actor',record.get('name'))
    bar=cards.verticalScrollBar() if cards.isWrapping() else cards.horizontalScrollBar()
    position=bar.value();current=cards.currentItem();selected=key(current.data(Qt.ItemDataRole.UserRole)) if current else None
    existing={key(cards.item(i).data(Qt.ItemDataRole.UserRole)):cards.item(i) for i in range(cards.count())}
    anchor=None;offset=0
    if preserve and position:
        for i in range(cards.count()):
            item=cards.item(i);rect=cards.visualItemRect(item)
            if rect.intersects(cards.viewport().rect()):
                anchor=key(item.data(Qt.ItemDataRole.UserRole));offset=rect.top() if cards.isWrapping() else rect.left();break
    updates=cards.updatesEnabled()
    if updates:cards.setUpdatesEnabled(False)
    blocked=bar.blockSignals(True)
    try:
        for index,record in enumerate(records):
            identifier=key(record);item=existing.get(identifier)
            if item is None:item=QListWidgetItem();cards.insertItem(index,item)
            elif cards.row(item)!=index:cards.insertItem(index,cards.takeItem(cards.row(item)))
            if item.data(Qt.ItemDataRole.UserRole)!=record:item.setData(Qt.ItemDataRole.UserRole,record)
            item.setToolTip((record.get('title') or record.get('name',''))+'\n'+'\n'.join(record.get('reasons',[])))
        while cards.count()>len(records):cards.takeItem(cards.count()-1)
        cards.doItemsLayout()
        wanted=existing.get(selected) if preserve else None
        if wanted is not None and cards.row(wanted)>=0:cards.setCurrentItem(wanted)
        elif not preserve:cards.setCurrentRow(-1)
        bar.setValue(position if preserve else 0)
        item=existing.get(anchor)
        if item is not None and cards.row(item)>=0:
            rect=cards.visualItemRect(item);bar.setValue(bar.value()+(rect.top() if cards.isWrapping() else rect.left())-offset)
    finally:
        bar.blockSignals(blocked)
        if updates:cards.setUpdatesEnabled(True)


class Job(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(object, object, str)

    def __init__(self, directory, function, parent=None):
        super().__init__(parent)
        self.directory, self.function = directory, function
        self.paused=threading.Event()
        self.budget=None
        self.background=False;self.resource='disk'

    def cancelled(self):
        if self.budget:self.budget.checkpoint(self.isInterruptionRequested)
        while self.paused.is_set() and not self.isInterruptionRequested():time.sleep(.1)
        return self.isInterruptionRequested()

    def run(self):
        library = None
        acquired=False
        try:
            if self.budget:
                self.progress.emit(0,0,'等待后台处理名额')
                self.budget.acquire(self.isInterruptionRequested,resource=self.resource,background=self.background);acquired=True
            library=Library(self.directory)
            library.parent_task_id=getattr(self,'task_identifier',None)
            last_report=[0,None];latest=[None]
            def report(done, total, message):
                if self.cancelled():raise ImportCancelled('任务已停止')
                latest[0]=(done,total,message)
                if time.monotonic()-last_report[0]>=.1 or total>0 and done>=total:
                    self.progress.emit(done,total,message);last_report[:]=[time.monotonic(),latest[0]]
            # A media subprocess must finish (or be cancelled) before yielding
            # its CPU/disk lease; pausing its polling loop would leave it running.
            def cancellable():return self.cancelled()
            cancellable.process_cancelled=self.isInterruptionRequested
            report.cancelled=cancellable
            library.cancelled=cancellable
            if self.cancelled():raise ImportCancelled('任务已停止')
            result=self.function(library, report)
            if latest[0] is not None and latest[0]!=last_report[1]:self.progress.emit(*latest[0])
            self.done.emit(result)
        except ImportCancelled:
            self.done.emit({"cancelled":True})
        except Exception as exc:
            self.failed.emit(str(exc))
            __import__('logging').exception('Background job failed')
        finally:
            if library:library.close()
            if acquired:self.budget.release()


def poster_regions(rect):
    image=rect.adjusted(8,8,-8,-82)
    return image,{'favorite':QRect(image.right()-38,image.top()+8,30,30),
                  'watchlist':QRect(image.right()-38,image.top()+44,30,30)}


class PosterList(QListWidget):
    favoriteRequested=Signal(int)
    watchlistRequested=Signal(int)
    actorPortraitDropped=Signal(object,str)
    def __init__(self, play, parent=None):
        super().__init__(parent)
        self.play = play
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def portrait_drop_path(self,event):
        urls=event.mimeData().urls()
        if not self.property('actorPortraitDrop') or len(urls)!=1 or not urls[0].isLocalFile():return None
        path=urls[0].toLocalFile()
        return path if Path(path).suffix.lower() in {'.jpg','.jpeg','.png','.webp','.bmp','.gif','.tif','.tiff','.avif'} else None

    def dragEnterEvent(self,event):
        if self.portrait_drop_path(event):event.setDropAction(Qt.DropAction.CopyAction);event.accept()
        elif event.mimeData().hasUrls():self.window().dragEnterEvent(event)
        else:super().dragEnterEvent(event)

    def dragMoveEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        data=item.data(Qt.ItemDataRole.UserRole) if item else {}
        if self.portrait_drop_path(event) and data and 'work_ids' in data:
            self.setCurrentItem(item);event.setDropAction(Qt.DropAction.CopyAction);event.accept()
        elif event.mimeData().hasUrls():self.window().dragMoveEvent(event)
        else:event.ignore()

    def dropEvent(self,event):
        path=self.portrait_drop_path(event);item=self.itemAt(event.position().toPoint())
        data=item.data(Qt.ItemDataRole.UserRole) if item else {}
        if path and data and 'work_ids' in data:
            event.setDropAction(Qt.DropAction.CopyAction);event.accept()
            self.actorPortraitDropped.emit(data,path)
        elif not path and event.mimeData().hasUrls():self.window().dropEvent(event)
        else:event.ignore()

    def wheelEvent(self,event):
        if not self.isWrapping():
            from .scrolling import route_vertical_wheel
            if route_vertical_wheel(self,event):return
        super().wheelEvent(event)

    def mouseMoveEvent(self,event):
        item=self.itemAt(event.position().toPoint());tip=''
        if item:
            data=item.data(Qt.ItemDataRole.UserRole) or {}
            if data.get('kind'):
                _,areas=poster_regions(self.visualItemRect(item))
                for key,area in areas.items():
                    if area.contains(event.position().toPoint()):tip=('取消' if data.get(key) else '加入')+('收藏' if key=='favorite' else '想看')
        self.setToolTip(tip)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.property('batchMode'):
            super().mouseReleaseEvent(event);return
        item = self.itemAt(event.position().toPoint())
        if item and event.button() == Qt.MouseButton.LeftButton:
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            rect,actions=poster_regions(self.visualItemRect(item))
            if data.get('kind'):
                for key,area in actions.items():
                    if area.contains(event.position().toPoint()):
                        (self.favoriteRequested if key=='favorite' else self.watchlistRequested).emit(data['id'])
                        return
            center = rect.center()
            point = event.position().toPoint()
            if data.get('files') and abs(point.x()-center.x()) < 27 and abs(point.y()-center.y()) < 27:
                self.play(data['id'])
                return
        super().mouseReleaseEvent(event)


class StillGallery(QListWidget):
    def wheelEvent(self,event):
        from .scrolling import route_vertical_wheel
        if not route_vertical_wheel(self,event):super().wheelEvent(event)


class PosterDelegate(QStyledItemDelegate):
    def __init__(self,parent):
        super().__init__(parent)
        from .images import image_cache
        image_cache().changed.connect(parent.viewport().update)

    def paint(self, painter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole) or {}
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(8, 8, -8, -8)
        image_rect = QRect(rect.x(), rect.y(), rect.width(), rect.height()-74)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        shape = QPainterPath()
        shape.addRoundedRect(image_rect, 3, 3)
        painter.setClipPath(shape)
        painter.fillRect(image_rect, QColor('#252525'))
        cover = data.get('_cover') or data.get('thumbnail') or data.get('photo_cache')
        from .images import image_cache
        ratio=self.parent().devicePixelRatioF();pixmap=image_cache().request(cover,image_rect.size()*ratio)
        if not pixmap.isNull():
            image = pixmap.scaled(image_rect.size()*ratio, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation);image.setDevicePixelRatio(ratio)
            painter.drawPixmap(round(image_rect.x()+(image_rect.width()-image.width()/ratio)/2),round(image_rect.y()+(image_rect.height()-image.height()/ratio)/2),image)
        else:
            painter.setPen(QColor('#777777'))
            painter.setFont(QFont('Segoe UI', 16))
            painter.drawText(image_rect.adjusted(18,18,-18,-18), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, data.get('title') or data.get('name','暂无封面'))
        if hover:
            painter.fillRect(image_rect, QColor(0,0,0,100))
            if data.get('files'):
                center = image_rect.center()
                painter.setBrush(QColor('#00a4dc'))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(center, 26, 26)
                icon('play','#ffffff',True).paint(painter,QRect(center.x()-12,center.y()-14,28,28))
        files = data.get('files',[])
        unfinished = data.get('_resume') or next((f for f in files if f.get('position',0)>0 and not f.get('completed')),None)
        if unfinished and unfinished.get('duration'):
            progress = min(1,unfinished['position']/unfinished['duration'])
            painter.fillRect(QRect(image_rect.x(),image_rect.bottom()-4,image_rect.width(),5), QColor(0,0,0,160))
            painter.fillRect(QRect(image_rect.x(),image_rect.bottom()-4,int(image_rect.width()*progress),5), QColor('#00a4dc'))
        if data.get('kind')=='series' and files:
            badge=QRect(image_rect.x()+8,image_rect.y()+8,48,25)
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(0,0,0,180));painter.drawRoundedRect(badge,12,12)
            painter.setPen(QColor('white'));painter.setFont(QFont('Segoe UI',9));painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,f'{len(files)} 集')
        if data.get('kind'):
            _,actions=poster_regions(option.rect)
            for key,name,color in [('favorite','heart','#f4779b'),('watchlist','bookmark','#65d3ed')]:
                if hover or data.get(key):
                    area=actions[key]
                    icon(name,color if data.get(key) else '#eeeeee',bool(data.get(key))).paint(painter,area.adjusted(6,6,-6,-6))
        painter.setClipping(False)
        if selected:
            painter.setPen(QColor('#00a4dc'))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(image_rect,3,3)
        painter.setPen(QColor('#eeeeee'));painter.setFont(QFont('Segoe UI',11))
        title=data.get('title') or data.get('name','')
        painter.drawText(QRect(rect.x(),image_rect.bottom()+8,rect.width(),23),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,painter.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,rect.width()-2))
        painter.setPen(QColor('#9999a3'));painter.setFont(QFont('Segoe UI',9))
        subtitle=data.get('_subtitle') or str(data.get('year') or '')
        source=next((source for source in data.get('sources',[]) if source.get('rating') is not None),None)
        meta=QRect(rect.x(),image_rect.bottom()+33,rect.width()-(54 if source else 0),19)
        painter.drawText(meta,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,painter.fontMetrics().elidedText(subtitle,Qt.TextElideMode.ElideRight,meta.width()))
        if source:
            star=QRect(rect.right()-47,image_rect.bottom()+35,14,14);icon('star','#e7c567',True).paint(painter,star)
            painter.setPen(QColor('#e7c567'));painter.drawText(QRect(rect.right()-29,image_rect.bottom()+33,30,19),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,f"{source['rating']:.1f}")
        if data.get('kind') and data.get('rating') is not None:
            painter.setPen(QColor('#adb8c8'));painter.drawText(QRect(rect.x(),image_rect.bottom()+53,rect.width(),18),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,f"我的评分  {data['rating']}")
        painter.restore()

    def sizeHint(self, option, index):
        data = index.data(Qt.ItemDataRole.UserRole) or {}
        width=data.get('_card_width',280 if data.get('_landscape') else 190)
        return QSize(width,round((width-16)*(9/16 if data.get('_landscape') else 3/2))+90)


class TagCompleter(QCompleter):
    def __init__(self, combo):
        super().__init__(combo.model(), combo)
        self.combo = combo

    def splitPath(self, path):
        return [path.replace('，', ',').rsplit(',', 1)[-1].strip()]

    def pathFromIndex(self,index):
        return self.combo.completed_text(super().pathFromIndex(index))


class FilterCombo(QComboBox):
    """Editable, contains-matching dropdown; tag fields also accept comma lists."""
    def __init__(self, values, text='', multiple=False):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.addItem('')
        self.addItems([str(value) for value in values])
        self.setEditText(str(text))
        self.multiple = multiple
        self.entered = str(text)
        if multiple: self.setCompleter(TagCompleter(self))
        self.lineEdit().textEdited.connect(self.remember)
        self.textActivated.connect(self.chosen)
        self.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer().popup().setStyleSheet('QAbstractItemView { background: #222228; color: #eeeeee; selection-background-color: #214655; border: 1px solid #46464f; padding: 4px; outline: 0; } QAbstractItemView::item { padding: 7px 10px; }')
        self.completer().popup().setMaximumWidth(600)
        self.lineEdit().setPlaceholderText('输入搜索或下拉选择' + ('，可多选' if multiple else ''))
        self.setMaxVisibleItems(10)
        self.setMinimumContentsLength(10)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.lineEdit().setClearButtonEnabled(True)

    def remember(self, value):
        self.entered = value

    def completed_text(self,value):
        if not value:return ''
        if ',' in value:return value
        parts=[part.strip() for part in self.entered.replace('，',',').split(',')]
        if parts and self.findText(parts[-1])<0:parts.pop()
        values=[part for part in parts if part]
        if value not in values:values.append(value)
        return ', '.join(values)

    def setEditText(self,text):
        self.entered=str(text)
        super().setEditText(str(text))

    def chosen(self,value):
        if self.multiple:self.setEditText(self.completed_text(value))
        self.entered=self.currentText()

    def text(self):
        return self.currentText().strip()

    def value(self):
        return int(self.text()) if self.text().isdigit() else 0


def filter_tokens(filters):
    tokens=[]
    kinds=filters.get('kinds')
    if kinds is not None and set(kinds)!=set(KINDS):tokens.append(('kinds',None,'分类：'+' / '.join(KINDS[kind] for kind in kinds if kind in KINDS)))
    if filters.get('query'):tokens.append(('query',None,'搜索：'+filters['query']))
    for key,prefix in [('tags_all',''),('tags_any','任一：'),('tags_not','排除：')]:
        for value in filters.get(key,[]):tokens.append((key,value,prefix+value))
    if filters.get('actor'):tokens.append(('actor',None,filters['actor']))
    low,high=filters.get('year_min'),filters.get('year_max')
    if low or high:tokens.append(('years',None,str(low) if low==high else f"{low or '最早'} — {high or '至今'}"))
    if filters.get('favorite'):tokens.append(('favorite',None,'已收藏'))
    if filters.get('disliked'):tokens.append(('disliked',None,'不喜欢'))
    if filters.get('watch_state'):tokens.append(('watch_state',None,{'unwatched':'未开始','progress':'观看中','completed':'已完成'}.get(filters['watch_state'],'')))
    if filters.get('watched'):tokens.append(('watched',None,'已观看' if filters['watched']=='yes' else '未观看'))
    if filters.get('watchlist'):tokens.append(('watchlist',None,'想看'))
    if filters.get('folder'):tokens.append(('folder',None,'目录：'+Path(filters['folder']).name))
    for key,title in [('rating_min','评分 ≥ '),('rating_max','评分 ≤ ')]:
        if filters.get(key):tokens.append((key,None,title+str(filters[key])))
    return tokens


class FilterDialog(QDialog):
    def __init__(self, filters, parent=None, options=None):
        super().__init__(parent)
        self.setObjectName('filterPanel')
        self.setWindowTitle('筛选媒体库')
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
        self.resize(500,740)
        self.original=dict(filters)
        options=options or {}
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        header=QHBoxLayout();header.setContentsMargins(24,20,16,8)
        title=QVBoxLayout();title.addWidget(label('筛选媒体库','panelTitle'));title.addWidget(label('组合条件，找到想看的那一部','subtitle'))
        header.addLayout(title,1);header.addWidget(ActionButton('关闭筛选','close',self.reject).icon_only())
        outer.addLayout(header)
        self.facet_status=label('','subtitle');self.facet_status.setContentsMargins(24,0,24,0);self.facet_status.hide();outer.addWidget(self.facet_status)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(24,12,24,20);layout.setSpacing(10);scroll.setWidget(content);outer.addWidget(scroll,1)
        self.scroll=scroll
        def field(title,control,parent=layout):
            column=QVBoxLayout();column.setSpacing(5);column.addWidget(label(title,'filterLabel'));column.addWidget(control);parent.addLayout(column)
        self.query=QLineEdit(filters.get('query',''));self.query.setClearButtonEnabled(True);self.query.setPlaceholderText('标题、别名或文件路径')
        self.types={};layout.addWidget(label('媒体分类','filterLabel'));scopes=QHBoxLayout();scopes.setSpacing(6)
        for kind,title in KINDS.items():
            control=QPushButton(title);control.setObjectName('scopeChip');control.setCheckable(True);control.setChecked(kind in filters.get('kinds',KINDS));self.types[kind]=control;scopes.addWidget(control)
        layout.addLayout(scopes)
        self.fields={'tags_all':FilterCombo(options.get('tags',[]),', '.join(filters.get('tags_all',[])),multiple=True)}
        field('标签',self.fields['tags_all'])
        self.selected_tags=QWidget();self.tag_flow=FlowLayout(self.selected_tags);layout.addWidget(self.selected_tags)
        self.fields['tags_all'].currentTextChanged.connect(self.update_tags)
        self.actor=FilterCombo(options.get('actors',[]),filters.get('actor',''));field('演员',self.actor)
        self.numbers={};years=QHBoxLayout()
        for key,title in [('year_min','起始年份'),('year_max','截止年份')]:
            control=FilterCombo(options.get('years',[]),filters.get(key) or '');self.numbers[key]=control;field(title,control,years)
        layout.addLayout(years)
        self.watched=QComboBox()
        for title,value in [('全部观看状态',''),('未开始','unwatched'),('观看中','progress'),('已完成','completed')]:self.watched.addItem(title,value)
        self.watched.setCurrentIndex(max(0,self.watched.findData(filters.get('watch_state',''))))
        status_row=QHBoxLayout();field('观看状态',self.watched,status_row)
        self.favorite=ActionButton('仅看已收藏','heart',checked=bool(filters.get('favorite')),accent='#f4779b');self.favorite.setObjectName('favoriteAction');field('收藏',self.favorite,status_row);layout.addLayout(status_row)
        self.disliked=ActionButton('仅看不喜欢','ban',checked=bool(filters.get('disliked')));self.disliked.setObjectName('dislikedFilter');field('不喜欢',self.disliked)
        self.disliked.toggled.connect(lambda checked:self.favorite.setChecked(False) if checked else None)
        self.favorite.toggled.connect(lambda checked:self.disliked.setChecked(False) if checked else None)
        self.advanced_toggle=ActionButton('高级条件','chevron',lambda:self.show_advanced(not self.advanced.isVisible()))
        layout.addWidget(self.advanced_toggle)
        self.advanced=QFrame();self.advanced.setObjectName('advancedFilters');advanced=QVBoxLayout(self.advanced);advanced.setContentsMargins(12,12,12,12);advanced.setSpacing(12)
        field('关键词',self.query,advanced)
        for key,title in [('tags_any','包含任一标签'),('tags_not','排除标签')]:
            control=FilterCombo(options.get('tags',[]),', '.join(filters.get(key,[])),multiple=True);self.fields[key]=control;field(title,control,advanced)
        ratings=QHBoxLayout()
        for key,title in [('rating_min','最低个人评分'),('rating_max','最高个人评分')]:
            control=QSpinBox();control.setRange(0,10);control.setSpecialValueText('不限');control.setValue(filters.get(key) or 0);self.numbers[key]=control;field(title,control,ratings)
        advanced.addLayout(ratings)
        self.folder=QLineEdit(filters.get('folder',''));self.folder.setClearButtonEnabled(True);self.folder.setPlaceholderText('仅搜索指定文件夹')
        directory=QHBoxLayout();directory.addWidget(self.folder,1);directory.addWidget(ActionButton('选择目录','folder',self.choose_folder).icon_only())
        advanced.addWidget(label('目录范围','filterLabel'));advanced.addLayout(directory)
        layout.addWidget(self.advanced);layout.addStretch(1)
        self.show_advanced(any(filters.get(key) for key in ['tags_any','tags_not','rating_min','rating_max','folder']))
        footer=QFrame();footer.setObjectName('filterFooter');actions=QHBoxLayout(footer);actions.setContentsMargins(24,14,24,14)
        actions.addWidget(ActionButton('重置','close',self.reset));actions.addStretch();apply=button('应用筛选',self.accept,True);apply.setMinimumWidth(160);apply.setMinimumHeight(42);actions.addWidget(apply);outer.addWidget(footer)
        self.update_tags()

    def set_options(self,options):
        for control,values in [*((control,options.get('tags',[])) for control in self.fields.values()),
                               (self.actor,options.get('actors',[])),
                               *((self.numbers[key],options.get('years',[])) for key in ('year_min','year_max'))]:
            text=control.currentText();control.blockSignals(True)
            control.clear();control.addItem('');control.addItems([str(value) for value in values]);control.setEditText(text)
            control.blockSignals(False)
        self.update_tags();self.facet_status.hide()

    def showEvent(self,event):
        super().showEvent(event)
        parent=self.parentWidget()
        if parent is not None:
            window=parent.window();origin=window.mapToGlobal(QPoint(0,0));width=min(500,window.width());height=max(420,window.height()-68)
            self.setGeometry(origin.x()+window.width()-width,origin.y()+68,width,height)

    def show_advanced(self,visible):
        self.advanced.setVisible(bool(visible));self.advanced_toggle.setText('收起高级条件' if visible else '高级条件')

    def update_tags(self,*_):
        clear(self.tag_flow)
        values=list(dict.fromkeys(value.strip() for value in self.fields['tags_all'].text().replace('，',',').split(',') if value.strip()))
        for value in values:
            self.tag_flow.addWidget(chip(value,lambda checked=False,value=value:self.remove_tag(value),True))
        self.selected_tags.setVisible(bool(values))

    def remove_tag(self,value):
        values=[part.strip() for part in self.fields['tags_all'].text().replace('，',',').split(',') if part.strip() and part.strip()!=value]
        self.fields['tags_all'].setEditText(', '.join(values))

    def reset(self):
        self.original.pop('watchlist',None)
        self.query.clear();self.actor.setEditText('');self.folder.clear();self.favorite.setChecked(False);self.disliked.setChecked(False);self.watched.setCurrentIndex(0)
        for field in self.fields.values():field.setEditText('')
        for field in self.numbers.values():
            if isinstance(field,FilterCombo):field.setEditText('')
            else:field.setValue(0)
        for control in self.types.values():control.setChecked(True)
        self.show_advanced(False)

    def accept(self):
        for key in ('year_min','year_max'):
            field=self.numbers[key]
            if field.text() and not 1800<=field.value()<=2200:
                QMessageBox.information(self,'年份','请选择或输入 1800–2200 的年份，留空表示不限。');return
        if self.numbers['year_min'].value() and self.numbers['year_max'].value() and self.numbers['year_min'].value()>self.numbers['year_max'].value():
            QMessageBox.information(self,'年份','起始年份不能晚于截止年份。');return
        if self.numbers['rating_min'].value() and self.numbers['rating_max'].value() and self.numbers['rating_min'].value()>self.numbers['rating_max'].value():
            QMessageBox.information(self,'评分','最低评分不能高于最高评分。');return
        if not any(control.isChecked() for control in self.types.values()):
            QMessageBox.information(self,'媒体分类','请至少选择一个分类。');return
        super().accept()

    def choose_folder(self):
        from .dialogs import existing_directory
        path=existing_directory(self,'选择目录范围',self.folder.text())
        if path:self.folder.setText(path)

    def filters(self):
        return {'query':self.query.text().strip(),'kinds':[key for key,control in self.types.items() if control.isChecked()],
                **{key:list(dict.fromkeys(part.strip() for part in field.text().replace('，',',').split(',') if part.strip())) for key,field in self.fields.items()},
                **{key:field.value() for key,field in self.numbers.items() if field.value()},
                'watch_state':self.watched.currentData(),'folder':self.folder.text().strip(),'actor':self.actor.text(),
                **({'watchlist':True} if self.original.get('watchlist') else {}),
                **({'disliked':True} if self.disliked.isChecked() else {}),
                **({'favorite':True} if self.favorite.isChecked() else {})}


class MetadataLinks(QWidget):
    linkActivated=Signal(str)


class CoverImage(QLabel):
    activated=Signal()
    stepped=Signal(int)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('点击放大封面 · 左右方向键切图 · 滚轮缩放 / 拖动查看')
        self.setAccessibleName('放大封面')

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit();event.accept();return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right):
            self.stepped.emit(-1 if event.key()==Qt.Key.Key_Left else 1);event.accept();return
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):
            self.activated.emit();event.accept();return
        super().keyPressEvent(event)


class Details(QWidget):
    def __init__(self, window, work_id):
        super().__init__(window)
        self.window, self.library, self.work_id = window, window.library, work_id
        self.work = self.library.work(work_id)
        w = self.work
        self.setWindowTitle(w['title'])
        self.resize(1050, 800)
        # A portrait cover is never enlarged into the background.
        self.backdrop = QPixmap()
        self.backdrop_paths=[w['metadata'].get('nfo_backdrop')]
        self.backdrop_paths.extend(str(self.library.directory/'cache'/(file['digest']+'.jpg')) for file in w['files'])
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)
        outer.addWidget(ActionButton('返回上一页','back',self.accept),alignment=Qt.AlignmentFlag.AlignLeft)
        self.setMinimumWidth(0)
        top = self.header_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight);top.setSpacing(20)
        poster = self.poster = CoverImage()
        poster_width=min(210,self.library.setting('poster_width',190)+20)
        poster.setFixedSize(poster_width, round(poster_width*1.5))
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setScaledContents(False)
        poster.setStyleSheet('background: #181818; border: none;')
        self.poster_path=self.library.setting(f'artwork_{work_id}',{}).get('poster') or w['thumbnail']
        poster.activated.connect(self.view_cover)
        poster.stepped.connect(self.step_cover)
        top.addWidget(poster,0,Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout();info.setSpacing(12)
        heading=label(w['title'],'detailTitle');heading.setMinimumWidth(0);heading.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);heading.setTextFormat(Qt.TextFormat.PlainText);heading.setWordWrap(True)
        heading.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        heading.setFocusPolicy(Qt.FocusPolicy.StrongFocus);info.addWidget(heading)
        facts=FlowLayout(spacing=12)
        if w['kind']!='fans':facts.addWidget(label(str(w['year'] or '年份待补充'),'subtitle'))
        facts.addWidget(label('Fans · 作者文件夹' if w['kind']=='fans' else KINDS[w['kind']],'subtitle'))
        duration=sum(file['duration'] for file in w['files']) if w['kind']=='fans' else max((file['duration'] for file in w['files']),default=0)
        if w['kind']=='fans':facts.addWidget(label(f"{len(w['files'])} 个视频",'subtitle'))
        if duration:facts.addWidget(label(f'{duration/60:.0f} 分钟','subtitle'))
        source=next((source for source in w['sources'] if source.get('rating') is not None),None)
        if source:facts.addWidget(label(f"★ {source['rating']:.1f}",'sourceScore'))
        info.addLayout(facts)
        actions=FlowLayout(spacing=8)
        play=button('播放' if not any(file['position'] for file in w['files']) else '继续播放',lambda:window.play_work(work_id),True)
        play.setIcon(icon('play','#ffffff',True));play.setMinimumHeight(46);play.setMinimumWidth(170);play.setEnabled(bool(w['files']));actions.addWidget(play)
        self.favorite_action=ActionButton('已收藏' if w['favorite'] else '收藏','heart',checked=bool(w['favorite']),accent='#f4779b');self.favorite_action.setObjectName('favoriteAction')
        self.favorite_action.clicked.connect(lambda value:self.personal(favorite=value));actions.addWidget(self.favorite_action)
        self.watchlist_action=ActionButton('已想看' if w['watchlist'] else '想看','bookmark',checked=bool(w['watchlist']))
        self.watchlist_action.clicked.connect(lambda value:self.personal(watchlist=value));actions.addWidget(self.watchlist_action)
        self.rating_action=ActionButton(f"{w['rating']} 分" if w['rating'] else '评分','star',self.choose_rating,accent='#e7c567');self.rating_action.setVisible(w['kind']!='other');self.rating_action.setToolTip('我的评分');self.rating_action.setAccessibleName('我的评分');actions.addWidget(self.rating_action)
        more=ActionButton('更多操作','more');self.management_menu=QMenu(more)
        playback=self.management_menu.addMenu('播放与观看')
        playback.addAction('从头播放',lambda:window.catalog_restart(work_id))
        playback.addAction('加入电脑播放队列',lambda:window.library.edit_queue([*window.library.setting('queue',{'ids':[]})['ids'],work_id]))
        playback.addSeparator()
        playback.addAction('整部标记已看',lambda:window.catalog_watch(work_id,'completed'))
        playback.addAction('整部重置进度',lambda:window.catalog_watch(work_id,'unwatched'))
        self.dislike_action=playback.addAction(icon('ban'),'不感兴趣');self.dislike_action.setCheckable(True);self.dislike_action.setChecked(bool(w['disliked']));self.dislike_action.triggered.connect(lambda value:self.personal(disliked=value))
        metadata=self.management_menu.addMenu('资料与图片')
        if w['kind'] in {'movie','series','vr'}:
            metadata.addAction(icon('search'),'刮削匹配…',self.scrape)
            metadata.addAction('编辑资料 / 锁定…',self.edit)
            metadata.addAction('导出 NFO 与图片…',lambda:window.export_nfo([work_id]))
            metadata.addSeparator()
        if w['kind']!='fans':
            metadata.addAction('从 NFO 补充图片…',lambda:window.import_nfo_artwork(work_id))
            metadata.addAction('刮削演员头像…',self.scrape_actor_photo)
        metadata.addAction('重新截取封面…',self.recapture)
        metadata.addAction('选择海报 / 缩略图…',self.choose_artwork)
        metadata.addAction('恢复默认海报 / 缩略图',self.reset_artwork)
        files_menu=self.management_menu.addMenu('文件与版本')
        files_menu.addAction(icon('folder'),'整理文件…',self.organize)
        if w['kind'] in {'movie','vr'}:files_menu.addAction('版本对比 / 默认播放…',lambda:window.compare_versions([work_id]))
        if w['files']:files_menu.addAction('扫描本地文件变化…',self.refresh_files)
        if w['kind'] in {'movie','series','vr'}:files_menu.addAction('合并重复作品…',self.merge_duplicate)
        if w['kind']=='fans':files_menu.addAction('合并同作者文件夹…',self.merge_fans_folders)
        if w['kind'] in {'movie','series','vr','fans'}:
            from .merge_ui import show_merge_history
            files_menu.addAction('合并记录 / 撤销…',lambda:show_merge_history(self))
        self.management_menu.addSeparator()
        self.management_menu.addAction('仅移出媒体库…',lambda:window.remove_catalog_work(work_id))
        if w['files']:self.management_menu.addAction('删除本地文件…',lambda:window.delete_work_files(work_id))
        more.setMenu(self.management_menu);actions.addWidget(more);info.addLayout(actions)
        metadata_info=QVBoxLayout();metadata_info.setSpacing(8)
        def links(values,field):
            # Keep the navigation signal available for keyboard and assistive actions.
            widget=MetadataLinks();flow=FlowLayout(widget)
            if field=='actor' and values:
                caption=label('主演','eyebrow');caption.setMinimumHeight(30);flow.addWidget(caption)
            controls=[]
            limit=6 if field=='actor' else 8
            for index,value in enumerate(values):
                control=chip(value,lambda checked=False,index=index:widget.linkActivated.emit(str(index)));flow.addWidget(control);controls.append(control)
                control.setVisible(index<limit)
            if len(values)>limit:
                expand=chip(f'展开全部 {len(values)} 位演员' if field=='actor' else f'展开全部 {len(values)} 个标签');expand.setCheckable(True)
                def toggle(checked):
                    for index,control in enumerate(controls):control.setVisible(checked or index<limit)
                    expand.setText('收起' if checked else (f'展开全部 {len(values)} 位演员' if field=='actor' else f'展开全部 {len(values)} 个标签'))
                expand.toggled.connect(toggle);flow.addWidget(expand)
            widget.linkActivated.connect(lambda index:window.search_metadata(field,values[int(index)]))
            metadata_info.addWidget(widget);widget.setVisible(bool(values));return widget
        self.tag_links=links(w['metadata'].get('tags',[]),'tags_all')
        self.actor_links=links([actor['name'] for actor in w['metadata'].get('actors',[])],'actor')
        if w['kind'] in {'movie','series','vr'}:
            from .metadata_ui import edit_metadata_lists
            editors=QHBoxLayout()
            for title,field in [('编辑标签','tags'),('编辑演员','actors')]:
                control=button(title,lambda checked=False,field=field:edit_metadata_lists(window,work_id,field))
                control.setObjectName('editWork'+field.title());editors.addWidget(control)
            editors.addStretch();metadata_info.addLayout(editors)
        if w['metadata'].get('released'):info.addWidget(label('上映 / 首播  '+str(w['metadata']['released']),'subtitle'))
        description=label(('按作者归组，包含此作者文件夹及下级目录的视频。多个目录属于同一作者时，可在“更多操作”中合并，原始文件保留。' if w['kind']=='fans' else w['metadata'].get('overview','暂无简介，可通过刮削补充。')) if w['kind']!='other' else '保留原始目录结构。')
        description.setWordWrap(True);description.setMinimumWidth(0);description.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        full_description=description.text()
        if len(full_description)>100:
            description.setText(full_description[:100].rstrip()+'…')
            expand_description=button('展开简介',lambda:None);expand_description.setCheckable(True);expand_description.setObjectName('quietAction')
            def toggle_description(expanded):
                description.setText(full_description if expanded else full_description[:100].rstrip()+'…')
                expand_description.setText('收起简介' if expanded else '展开简介')
            expand_description.toggled.connect(toggle_description)
            info.addWidget(description);info.addWidget(expand_description,alignment=Qt.AlignmentFlag.AlignLeft)
        else:info.addWidget(description)
        info.addStretch()
        recommended=next((item for item in window.current_items if item.get('id')==work_id and item.get('reasons')),None)
        if recommended:
            reasons=label('推荐原因：'+'；'.join(recommended['reasons']),'subtitle');reasons.setWordWrap(True);info.addWidget(reasons)
        top.addLayout(info,1);outer.addLayout(top)
        divider=QFrame();divider.setObjectName('personalBar');divider.setFixedHeight(1);outer.addWidget(divider)
        self.files = QListWidget()
        for f in w['files']:
            title = ((f"S{f['season']:02} E{f['episode']:02}  ·  " if f['season'] is not None and f['episode'] is not None else '待补充季集  ·  ') if w['kind'] == 'series' else '') + (f.get('title') or Path(f['path']).name)
            duration_text = f"{f['duration']/60:.1f} 分钟" if f['duration'] > 0 else "时长待补充"
            item = QListWidgetItem(f"{title}   ·   {duration_text}   ·   上次 {f['position']/60:.1f} 分钟")
            item.setToolTip(f['path'])
            item.setData(Qt.ItemDataRole.UserRole, f)
            self.files.addItem(item)
        if self.files.count():self.files.setCurrentRow(0)
        self.files.itemDoubleClicked.connect(lambda item: window.play_file(item.data(Qt.ItemDataRole.UserRole)))
        self.files_heading=label('作者视频 · 双击播放' if w['kind']=='fans' else '视频文件 / 季与集 · 双击播放', 'subtitle')
        outer.addWidget(self.files_heading)
        if w['kind']=='series':
            self.season_filter=QComboBox();self.season_filter.addItem('全部季',None)
            for season in sorted({f['season'] for f in w['files'] if f['season'] is not None}):self.season_filter.addItem('特别篇' if season==0 else f'第 {season} 季',season)
            def choose_season():
                for i in range(self.files.count()):self.files.item(i).setHidden(self.season_filter.currentData() is not None and self.files.item(i).data(Qt.ItemDataRole.UserRole)['season']!=self.season_filter.currentData())
                for i in range(self.files.count()):
                    if not self.files.item(i).isHidden():self.files.setCurrentRow(i);break
            self.season_filter.currentIndexChanged.connect(choose_season);outer.addWidget(self.season_filter)
            self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            episode_actions=FlowLayout(spacing=8)
            self.remove_episodes_action=button('移除选中集…',lambda:self.remove_selected_episodes(False));episode_actions.addWidget(self.remove_episodes_action)
            self.remove_season_action=button('移除整季…',lambda:self.remove_selected_episodes(True));episode_actions.addWidget(self.remove_season_action)
            self.delete_episode_files_action=ActionButton('删除视频文件…','more')
            delete_menu=QMenu(self.delete_episode_files_action)
            delete_menu.addAction('删除选中集的本地视频…',lambda:self.delete_selected_episode_files(False))
            delete_menu.addAction('删除整季的本地视频…',lambda:self.delete_selected_episode_files(True))
            self.delete_episode_files_action.setMenu(delete_menu);episode_actions.addWidget(self.delete_episode_files_action)
            outer.addLayout(episode_actions)
        watch_row=QHBoxLayout()
        def mark_episode(state):
            item=self.files.currentItem()
            if item:self.library.set_watched(self.work_id,state,item.data(Qt.ItemDataRole.UserRole)['id']);self.window.open_details(self.work_id,fetch=False)
        watch_row.addWidget(button('当前视频标为已看',lambda:mark_episode('completed')));watch_row.addWidget(button('重置当前视频进度',lambda:mark_episode('unwatched')));outer.addLayout(watch_row)
        outer.addWidget(self.files)
        outer.addLayout(metadata_info)
        bookmark_row=QHBoxLayout();self.bookmark_heading=label('时间点书签 · 双击跳转','subtitle');bookmark_row.addWidget(self.bookmark_heading,1)
        self.add_bookmark_action=ActionButton('添加时间点书签','bookmark',self.add_bookmark);self.add_bookmark_action.setVisible(bool(w['files']));bookmark_row.addWidget(self.add_bookmark_action);outer.addLayout(bookmark_row)
        self.bookmark_empty=label('还没有时间点书签，可在此添加，或播放时点击“书签”。','subtitle');self.bookmark_empty.setWordWrap(True);outer.addWidget(self.bookmark_empty)
        self.bookmark_list=QListWidget();self.bookmark_list.setIconSize(QSize(144,81));self.bookmark_list.setMaximumHeight(260);outer.addWidget(self.bookmark_list)
        self.bookmark_list.itemDoubleClicked.connect(lambda row:window.play_file(row.data(Qt.ItemDataRole.UserRole)));self.refresh_bookmarks()
        self.files.setFixedHeight(min(200,max(56,len(w['files'])*44+12)))
        self.files.setVisible(bool(w['files']))
        self.files_heading.setVisible(bool(w['files']))
        self.episode_overview=label('')
        self.episode_overview.setWordWrap(True)
        outer.addWidget(self.episode_overview)
        self.files.itemClicked.connect(self.select_episode)
        self.files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self.episode_menu)
        sources = QVBoxLayout()
        for source in w['sources']:
            if source['plugin'] == 'local-nfo':
                sources.addWidget(label(f"本地 NFO · 来源评分 {source['rating'] if source['rating'] is not None else '未知'}"))
                continue
            title = f"{source['site']} · {source['source_id']} · 来源评分 {source['rating'] if source['rating'] is not None else '未知'}"
            control = button(title + '  ↗', lambda checked=False, url=source['url']: self.open_source(url))
            control.setToolTip(f"默认使用无痕 / 隐私窗口\n{source['url']}\n元数据更新：{source['updated']}\n站点收录：{source['site_added'] or '未知'}")
            sources.addWidget(control)
        if w['discovered']:
            sources.addWidget(label('首次发现：' + w['discovered'], 'subtitle'))
        outer.addLayout(sources)
        from .artwork import still_paths
        # The section is always part of the layout, even if an episode or refresh supplies images later.
        self.gallery_heading=label('剧照','sectionTitle')
        outer.addWidget(self.gallery_heading)
        self.still_gallery = StillGallery()
        self.still_gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.still_gallery.setFlow(QListWidget.Flow.LeftToRight)
        self.still_gallery.setWrapping(False)
        still_width=self.library.setting('thumbnail_width',280)+8
        still_height=round(still_width*9/16)
        self.still_gallery.setIconSize(QSize(still_width,still_height))
        self.still_gallery.setGridSize(QSize(still_width+20,still_height+30))
        self.still_gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.still_gallery.setFixedHeight(still_height+56)
        self.still_gallery.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.still_gallery.horizontalScrollBar().valueChanged.connect(self.render_artwork)
        outer.addWidget(self.still_gallery)
        self.still_gallery.itemClicked.connect(self.show_still)
        self.still_gallery.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.still_gallery.customContextMenuRequested.connect(self.still_artwork_menu)
        self.set_stills(still_paths(w))
        outer.addWidget(button('选择图片设为海报 / 缩略图…',self.choose_artwork))
        self.gallery_status=label('','subtitle')
        self.gallery_status.setWordWrap(True)
        outer.addWidget(self.gallery_status)
        requested=len(w['metadata'].get('stills',[]))
        shown=self.still_gallery.count()
        self.gallery_status.setText(f'已载入 {shown} 张剧照 · 点击放大，横向滚动查看更多' if shown else
            '剧照尚未缓存，可点击“刷新剧照与下载资源”重试。' if requested else '暂无剧照，可从来源加载详情，或导入本地 NFO / extrafanart。')
        self.resources_heading=label('下载资源','sectionTitle')
        outer.addWidget(self.resources_heading)
        from .downloads import download_folder
        film_download=w['kind'] in {'movie','series','vr'}
        self.download_directory_label=label('保存位置：'+str(download_folder(self.library,self.work_id)) if film_download else '')
        self.download_directory_label.setWordWrap(True)
        outer.addWidget(self.download_directory_label)
        directory_actions=QHBoxLayout()
        download_options=ActionButton('下载选项','more');download_menu=QMenu(download_options)
        download_menu.addAction('更改本片下载目录…',self.choose_download_folder)
        download_menu.addAction('恢复分类默认目录',self.reset_download_folder)
        download_menu.addSeparator();download_menu.addAction('检查下载文件并入库',self.import_downloads)
        download_options.setMenu(download_menu);directory_actions.addWidget(download_options);directory_actions.addStretch()
        outer.addLayout(directory_actions)
        self.download_directory_label.setVisible(film_download);download_options.setVisible(film_download);self.resources_heading.setVisible(film_download)
        self.resource_buttons=[]
        for entry in w['metadata'].get('download_url',[]):
            method=entry.get('method',w['metadata'].get('download_method'))
            text=entry.get('description') or ('磁力下载' if method=='magnet' else '直接下载')
            control=button(('磁力 · ' if method=='magnet' else '直链 · ')+text,
                           lambda checked=False,entry=entry:self.start_download(entry))
            control.setObjectName('resourceAction');control.setIcon(icon('folder'));self.resource_buttons.append(control);outer.addWidget(control)
        if not self.resource_buttons and film_download:
            outer.addWidget(label('来源尚未提供下载资源；可刷新来源详情。','subtitle'))
        self.refresh_resources=button('刷新剧照与下载资源',lambda:self.window.refresh_source_details(self.work_id))
        outer.addWidget(self.refresh_resources);self.refresh_resources.setVisible(film_download)
        if w['kind']=='fans':self.gallery_status.hide()
        if not self.work['files']:
            outer.addWidget(label('此影片尚未入库。查看剧照和下载资源无需先导入视频。','subtitle'))
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(button('返回上一页', self.accept))
        outer.addLayout(bottom)
        from .images import image_cache
        image_cache().changed.connect(self.render_artwork)
        for text in self.findChildren(QLabel):
            if text is not self.poster:
                text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.render_artwork()

    def refresh_bookmarks(self):
        entries=self.library.db.execute('SELECT b.* FROM bookmarks b JOIN files f ON f.id=b.file_id WHERE f.work_id=? ORDER BY b.file_id,b.position LIMIT 300',(self.work_id,)).fetchall()
        self.bookmark_list.clear();files_by_id={file['id']:file for file in self.work['files']}
        for entry in entries:
            file=files_by_id.get(entry['file_id'])
            if not file:continue
            row=QListWidgetItem(f"{Path(file['path']).name} · {int(entry['position'])//60:02}:{int(entry['position'])%60:02} · {entry['title']}\n{entry['note']}")
            row.setData(Qt.ItemDataRole.UserRole,{**file,'position':entry['position'],'completed':0})
            if entry['image']:row.setIcon(QIcon(entry['image']))
            self.bookmark_list.addItem(row)
        self.bookmark_list.setFixedHeight(min(260,max(110,len(entries)*104+8)))
        self.bookmark_heading.setVisible(bool(self.work['files']));self.bookmark_list.setVisible(bool(entries));self.bookmark_empty.setVisible(bool(self.work['files']) and not entries)

    def add_bookmark(self):
        if not self.work['files']:return
        item=self.files.currentItem();file=item.data(Qt.ItemDataRole.UserRole) if item else self.work['files'][0]
        self.window.player.add_bookmark(file=file,parent=self)

    def render_artwork(self):
        from .images import image_cache
        cache=image_cache()
        image=cache.request(self.poster_path,QSize(420,630))
        poster_key=(image.cacheKey(),self.poster.width(),self.poster.height())
        if not image.isNull() and getattr(self,'_poster_key',None)!=poster_key:
            self.poster.setPixmap(image.scaled(self.poster.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self._poster_key=poster_key
        for path in self.backdrop_paths:
            image=cache.request(path,QSize(1400,800))
            if not image.isNull() and image.width()>image.height():
                if self.backdrop.cacheKey()!=image.cacheKey():self.backdrop=image;self.update(QRect(0,0,self.width(),500))
                break
        visible=self.still_gallery.viewport().rect();near=visible.adjusted(-visible.width(),0,visible.width(),0)
        for index in range(self.still_gallery.count()):
            item=self.still_gallery.item(index)
            if not self.still_gallery.visualItemRect(item).intersects(near):
                if not item.icon().isNull():item.setIcon(QIcon());item.setData(Qt.ItemDataRole.UserRole+2,None)
                continue
            image=cache.request(item.data(Qt.ItemDataRole.UserRole),self.still_gallery.iconSize()*self.devicePixelRatioF())
            if not image.isNull() and item.data(Qt.ItemDataRole.UserRole+2)!=image.cacheKey():
                item.setIcon(QIcon(image));item.setData(Qt.ItemDataRole.UserRole+2,image.cacheKey())

    def open_source(self, url):
        from .private_browser import open_private
        try:
            open_private(url)
        except (ValueError, RuntimeError) as error:
            QMessageBox.information(self, '无痕浏览', str(error))

    def fullscreen_stills(self,item):
        if item is None:return
        from .catalog_ui import StillViewer
        viewer=StillViewer([self.still_gallery.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.still_gallery.count())],self.still_gallery.row(item),self)
        viewer.exec();viewer.deleteLater()

    def view_cover(self):
        if not self.poster_path:
            self.window.status.setText('此影片暂无封面，可从 NFO 补充或通过插件刮削。');return
        from .catalog_ui import StillViewer
        from .artwork_ui import artwork_paths
        paths=list(dict.fromkeys([self.poster_path,*artwork_paths(self.library,self.work)]))
        viewer=StillViewer(paths,parent=self,title='封面')
        viewer.exec();viewer.deleteLater()

    def step_cover(self,delta):
        from .artwork_ui import artwork_paths
        paths=artwork_paths(self.library,self.work)
        if not paths:return
        index=paths.index(self.poster_path) if self.poster_path in paths else 0
        self.poster_path=paths[(index+delta)%len(paths)];self.render_artwork()

    def still_artwork_menu(self,position):
        item=self.still_gallery.itemAt(position)
        if item is None:return
        menu=QMenu(self)
        menu.addAction('设为海报 / 缩略图…',lambda:self.choose_artwork(item.data(Qt.ItemDataRole.UserRole)))
        menu.exec(self.still_gallery.viewport().mapToGlobal(position))

    def choose_artwork(self,path=None):
        from .artwork_ui import ArtworkDialog,save_artwork
        dialog=ArtworkDialog(self.window,self.library.work(self.work_id),path if isinstance(path,str) else self.poster_path)
        if dialog.exec():
            work_id=self.work_id;window=self.window
            source,role,anchor=dialog.sources.currentData(),dialog.role.currentData(),dialog.anchor.currentData()
            def saved(_):
                window.reload_details(work_id)
            window.run_job('保存海报 / 缩略图',lambda lib,progress:save_artwork(lib,work_id,source,role,anchor),saved)
        dialog.deleteLater()

    def reset_artwork(self):
        self.library.set_setting(f'artwork_{self.work_id}',{})
        self.window.refresh();self.window.reload_details(self.work_id)

    def scrape_actor_photo(self):
        names=[actor['name'] for actor in self.work['metadata'].get('actors',[]) if actor.get('name')]
        name=''
        if len(names)==1:name=names[0]
        elif names:
            name,ok=QInputDialog.getItem(self,'演员头像','选择演员',names,0,False)
            if not ok:return
        from .actor_ui import show_actor_scraper
        show_actor_scraper(self.window,name)

    def merge_fans_folders(self):
        from .fans_ui import merge_author_folders
        merge_author_folders(self)

    def set_stills(self, paths, prefix='剧照'):
        self.still_gallery.clear()
        for path in dict.fromkeys(paths):
            item=QListWidgetItem(f'{prefix} {self.still_gallery.count()+1}')
            item.setData(Qt.ItemDataRole.UserRole,path)
            self.still_gallery.addItem(item)
        visible=bool(self.still_gallery.count())
        self.gallery_heading.setVisible(visible)
        self.still_gallery.setVisible(visible)
        if hasattr(self,'poster_path'):self.render_artwork()

    def select_episode(self, item):
        from .artwork import still_paths
        file=item.data(Qt.ItemDataRole.UserRole)
        self.episode_overview.setText(file.get('overview',''))
        self.set_stills(file.get('stills') or still_paths(self.work),'单集剧照' if file.get('stills') else '剧照')
        self.gallery_status.setText(f'已载入 {self.still_gallery.count()} 张剧照 · 点击放大' if self.still_gallery.count() else '此集暂无可显示的剧照。')

    def show_still(self, item):
        self.fullscreen_stills(item)

    def choose_download_folder(self):
        from .dialogs import existing_directory
        from .downloads import download_folder,set_download_folder
        path=existing_directory(self,'选择此作品的下载目录',str(download_folder(self.library,self.work_id)))
        if path:
            directory=set_download_folder(self.library,self.work_id,path)
            self.download_directory_label.setText('保存位置：'+directory)

    def reset_download_folder(self):
        from .downloads import set_download_folder
        self.download_directory_label.setText('保存位置：'+set_download_folder(self.library,self.work_id,''))

    def import_downloads(self):
        from .downloads import import_download_folder
        work_id=self.work_id
        def complete(result):
            self.window.reload_details(work_id)
            self.window.status.setText(f"下载入库：新增 {result['imported']} · 已入库 {result['duplicates']} · 待检查 {len(result['errors'])}")
            if result['errors']:
                QMessageBox.information(self.window,'部分下载尚未入库','请确认外部下载器已完成下载后重试。\n'+'\n'.join(item['path']+'：'+item['reason'] for item in result['errors'][:5]))
        self.window.run_job('检查下载文件并入库',lambda lib,p:import_download_folder(lib,work_id,p,p.cancelled),complete)

    def start_download(self, entry):
        from .downloads import download_to_library,launch_magnet
        work=self.window.library.work(self.work_id)
        try:index=work['metadata'].get('download_url',[]).index(entry)
        except ValueError:
            QMessageBox.information(self,'资源已变化','请刷新详情后重试。');return
        method=entry.get('method',work['metadata'].get('download_method'))
        work_id=self.work_id
        if method=='magnet':
            def launched(result):
                message='已交给 '+result['client']+'，保存位置：'+result['directory']
                if not result['directory_sent']:
                    QApplication.clipboard().setText(result['directory'])
                    message+='\n'+result['message']+' 已复制目录路径。'
                message+='\n外部下载完成后，点击“检查下载文件并入库”。'
                if self.window.detail_page is not None and self.window.detail_page.work_id==work_id:
                    self.window.detail_page.gallery_status.setText(message)
                self.window.status.setText('磁力下载任务已交给外部工具')
            self.window.run_job('启动磁力下载器',lambda lib,p:launch_magnet(lib,work_id,index),launched)
        else:
            def complete(result):
                self.window.reload_details(work_id)
                self.window.status.setText('下载完成并已关联影视资料：'+result['path'])
            self.window.run_job('直接下载并入库',lambda lib,p:download_to_library(lib,work_id,index,p,p.cancelled),complete)

    def accept(self):
        if self.window.detail_page is self:
            self.window.back_details()
        else:
            self.close()

    def resizeEvent(self,event):
        available=self.width()-48
        stacked=available<610
        self.header_layout.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        width=min(150 if stacked else 210,max(120,round(available*.26)),self.library.setting('poster_width',190)+20)
        if self.poster.width()!=width:self.poster.setFixedSize(width,round(width*1.5))
        super().resizeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101010'))
        if not self.backdrop.isNull():
            area = QRect(0, 0, self.width(), min(500, self.height()))
            painter.save()
            painter.setClipRect(area)
            key=(self.backdrop.cacheKey(),area.width(),area.height())
            if getattr(self,'_backdrop_key',None)!=key:
                ratio=area.width()/max(1,area.height());width=self.backdrop.width();height=self.backdrop.height()
                crop_width=min(width,max(1,round(height*ratio)));crop_height=min(height,max(1,round(width/ratio)))
                cropped=self.backdrop.copy((width-crop_width)//2,(height-crop_height)//2,crop_width,crop_height)
                self._backdrop_image=cropped.scaled(area.size(),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation);self._backdrop_key=key
            image=self._backdrop_image
            painter.drawPixmap((area.width()-image.width())//2, (area.height()-image.height())//2, image)
            painter.fillRect(area, QColor(0, 0, 0, 165))
            fade = QLinearGradient(0, 100, 0, area.height())
            fade.setColorAt(0, QColor(16,16,16,0))
            fade.setColorAt(1, QColor('#101010'))
            painter.fillRect(area, fade)
            painter.restore()

    def choose_rating(self):
        menu=QMenu(self.rating_action)
        for value in range(10,0,-1):
            action=menu.addAction(f"{'★' if self.work['rating']==value else '☆'}  {value} 分")
            action.triggered.connect(lambda checked=False,value=value:self.personal(rating=value))
        menu.addSeparator();menu.addAction('清除评分',lambda:self.personal(rating=None))
        menu.exec(self.rating_action.mapToGlobal(QPoint(0,self.rating_action.height())))

    def sync_personal(self):
        self.work=self.library.work(self.work_id)
        self.favorite_action.setChecked(bool(self.work['favorite']));self.favorite_action.setText('已收藏' if self.work['favorite'] else '收藏')
        self.watchlist_action.setChecked(bool(self.work['watchlist']));self.watchlist_action.setText('已想看' if self.work['watchlist'] else '想看')
        self.rating_action.setText(f"{self.work['rating']} 分" if self.work['rating'] else '评分')
        self.dislike_action.setChecked(bool(self.work['disliked']))

    def personal(self, **fields):
        try:self.library.update_personal(self.work_id,**fields)
        except Exception as error:
            self.favorite_action.setChecked(bool(self.work['favorite']));self.watchlist_action.setChecked(bool(self.work['watchlist']))
            QMessageBox.warning(self,'未保存',str(error));return
        self.sync_personal()
        self.window.refresh()
        self.window.status.setText('已保存 · '+('已收藏' if fields.get('favorite') else '已取消收藏' if 'favorite' in fields else '个人偏好已更新'))

    def edit(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑元数据 · 勾选字段在刷新时保留')
        dialog.resize(650, 720)
        layout = QVBoxLayout(dialog)
        from .metadata_ui import MetadataList
        from .metadata_edit import snapshot
        original=snapshot(self.library,self.work_id)
        title = QLineEdit(self.work['title'])
        layout.addWidget(label('影片名称'))
        layout.addWidget(title)
        year = QSpinBox()
        year.setRange(0, 2100)
        year.setSpecialValueText('未知')
        year.setValue(self.work['year'] or 0)
        layout.addWidget(label('年份'))
        layout.addWidget(year)
        overview = QPlainTextEdit(self.work['metadata'].get('overview', ''))
        overview.setMaximumHeight(120)
        layout.addWidget(label('简介'));layout.addWidget(overview)
        from PySide6.QtWidgets import QTabWidget
        lists=QTabWidget();layout.addWidget(lists)
        tags=MetadataList('tags',original.get('tags',[]));lists.addTab(tags,'标签')
        actors=MetadataList('actors',original.get('actors',[]));lists.addTab(actors,'演员')
        row = QHBoxLayout()
        locks = {}
        for field in ['title', 'year', 'tags', 'overview', 'actors', 'poster']:
            check = QCheckBox({'title':'名称','year':'年份','tags':'标签','overview':'简介','actors':'演员','poster':'海报'}[field])
            check.setChecked(field in self.work['locked'])
            row.addWidget(check)
            locks[field] = check
        layout.addWidget(label('锁定字段'))
        layout.addLayout(row)
        def save():
            try:
                from .metadata_edit import normalize
                people=normalize('actors',actors.values)
                tag_values=normalize('tags',tags.values)
                for field,value in [('tags',tag_values),('actors',people)]:
                    if value!=original.get(field,[]):locks[field].setChecked(True)
                if not title.text().strip():
                    raise ValueError('名称不能为空')
                self.library.edit_metadata(self.work_id, {'title': title.text().strip(), 'year': year.value() or None,
                    'tags': tag_values, 'overview': overview.toPlainText(), 'actors': people},
                    [k for k, c in locks.items() if c.isChecked()])
                dialog.accept()
                self.accept()
                self.window.refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, '资料未保存', str(exc))
        layout.addWidget(button('保存资料', save, True))
        dialog.exec()

    def merge_duplicate(self):
        from .merge_ui import merge_catalog_work
        return merge_catalog_work(self)

    def scrape(self):
        available = [p for p in Plugins(self.library).installed() if p['config'].get('enabled') and self.work['kind'] in p.get('media_kinds', ['movie','series','vr']) and ('search' in p['capabilities'] or 'detail' in p['capabilities'])]
        if not available:
            QMessageBox.information(self, '刮削插件', '请先在设置 → 按需刮削引擎中安装并启用 Javinizer-Go，或启用支持搜索的站点插件。')
            return
        default = next((index for index, provider in enumerate(available) if self.work['kind'] in {'movie','vr'} and provider['id']=='javinizer-go'), 0)
        name, ok = QInputDialog.getItem(self, '刮削来源', '选择刮削来源', [p['name'] for p in available], default, False)
        if not ok:
            return
        plugin = next(p for p in available if p['name'] == name)
        initial = self.work['title']
        if plugin.get('engine') == 'javinizer-go':
            from .javinizer import work_query
            initial = work_query(self.work)
        text, ok = QInputDialog.getText(self, '匹配影片', plugin.get('input_hint', '输入关键词或完整详情页 URL'), text=initial)
        if not ok or not text.strip():
            return
        text = text.strip()
        operation = 'detail' if text.startswith(('https://', 'http://')) else 'search'
        if operation not in plugin['capabilities']:
            QMessageBox.information(self, '刮削来源', '此插件不支持关键词搜索，请输入完整详情页 URL。' if operation == 'search' else '此插件不支持详情链接，请输入关键词搜索。')
            return
        def complete(results):
            if self.window.detail_page is not self:
                return
            if not results:
                message = '所选来源未收录此番号，请核对番号或调整来源顺序。' if plugin.get('engine') else '未找到候选，请手动指定详情页'
                self.library.task(__import__('uuid').uuid4().hex, 'match', 'pending', {'work_id': self.work_id, 'plugin': plugin['id']}, error=message)
                QMessageBox.information(self.window, '待处理', message + '\n已记录到任务列表。')
                return
            from .matching import CandidatePicker, apply_match
            picker = CandidatePicker(self.library.directory, plugin['id'], results, self.window, allow_force=True)
            accepted = picker.exec()
            candidate = picker.selection()
            force = picker.force_overwrite()
            picker.deleteLater()
            if accepted and candidate is not None:
                work_id = self.work_id
                def saved(result):
                    if self.window.detail_page is not self:return
                    if isinstance(result,dict) and result.get('conflict'):
                        from .matching import MatchConflictDialog
                        conflict=result['conflict'];dialog=MatchConflictDialog(conflict,self.window)
                        accepted=dialog.exec();choice=dialog.choice;dialog.deleteLater()
                        if not accepted:return
                        if choice=='view':
                            self.window.open_details(conflict['related'][0]['id'],fetch=False);return
                        if choice=='merge':
                            from .merge_ui import preview_and_merge
                            preview_and_merge(self,[work['id'] for work in conflict['related']]);return
                        self.window.run_job('按选择更新刮削资料',
                            lambda lib,progress:apply_match(lib,plugin,'detail',result['candidate'],work_id,
                                cancelled=progress.cancelled,force=force,interactive=True,resolution=choice,snapshot=result['snapshot']),saved)
                        return
                    self.window.reload_details(work_id)
                    if isinstance(result,dict) and result.get('errors'):
                        QMessageBox.information(self.window,'部分图片未完成','影片资料已更新；以下图片可在资料修复中重试：\n'+'\n'.join(result['errors']))
                self.window.run_job('保存刮削资料与图片',
                    lambda lib, progress: apply_match(lib, plugin, operation, candidate, work_id, cancelled=progress.cancelled, force=force, interactive=True),
                    saved)
        self.window.run_job('搜索刮削来源', lambda lib, p: Plugins(lib).run(plugin['id'], operation, cancelled=p.cancelled, progress=p, refresh=True, **({'url': text.strip()} if operation == 'detail' else {'query': text.strip()})), complete)


    def organize(self):
        from .organize_ui import show_organizer
        return show_organizer(self)

    def refresh_files(self):
        origin=self.work_id
        def scan(lib, progress):
            return lib.refresh_work(origin, progress, progress.cancelled)
        def ready(result):
            if not isinstance(result, dict) or result.get('cancelled'):return
            if self.detail_page is not None and self.detail_page.work_id==origin:self.window.reload_details(origin)
            missing=result.get('missing',[]);renamed=result.get('renamed',[]);imported=result.get('imported',0)
            warnings=result.get('errors',[])
            summary=f"新增 {imported} 个 · 恢复重命名 {len(renamed)} 个 · 缺失 {len(missing)} 个"
            if warnings:summary+=f" · 警告 {len(warnings)}"
            dialog=QMessageBox(self.window);dialog.setWindowTitle('扫描文件变化')
            if missing:
                dialog.setText(summary+'。是否移除缺失文件的媒体库记录？磁盘上其他文件不受影响。')
                dialog.setDetailedText('\n'.join(missing))
                dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                dialog.button(QMessageBox.StandardButton.Ok).setText('移除缺失记录')
                dialog.button(QMessageBox.StandardButton.Cancel).setText('保留')
                if dialog.exec()==QMessageBox.StandardButton.Ok:
                    def apply(lib, progress):
                        work=lib.work(origin);wanted=set(missing)
                        return lib.remove_local_records(origin,[f['id'] for f in work['files'] if f['path'] in wanted])
                    def removed(result):
                        if result.get('removed_work'):self.window.back_details();self.window.refresh()
                        elif self.window.detail_page is not None and self.window.detail_page.work_id==origin:self.window.reload_details(origin)
                        self.window.status.setText(f"已移除 {result['removed']} 条缺失记录，文件保留在磁盘")
                    self.window.run_job('移除缺失记录',apply,removed)
            else:
                dialog.setText(summary);dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
                dialog.exec()
            dialog.deleteLater()
        self.window.run_job('扫描本地文件变化',scan,ready)

    def episode_menu(self, position):
        item=self.files.itemAt(position)
        if not item:return
        file=item.data(Qt.ItemDataRole.UserRole)
        menu=QMenu(self)
        menu.addAction('在系统文件夹中显示',lambda:self.window.reveal_file_path(file['path']))
        menu.addAction('移除此集的媒体库记录（保留文件）',lambda:self.remove_episode_records([file['id']]))
        if file.get('season') is not None:
            season=file['season']
            menu.addAction(f'移除第 {season} 季的全部记录（保留文件）' if season else '移除特别篇的全部记录（保留文件）',
                           lambda:self.remove_episode_records([f['id'] for f in self.work['files'] if f['season']==season]))
        menu.exec(self.files.mapToGlobal(position))

    def selected_episode_ids(self,whole_season=False):
        selected=[item.data(Qt.ItemDataRole.UserRole) for item in self.files.selectedItems() if not item.isHidden()]
        if whole_season:
            season=self.season_filter.currentData()
            if season is None and selected:season=selected[0].get('season')
            if season is None:
                QMessageBox.information(self.window,'选择季','请先选择一个季，或选择带有季号的视频。');return
            selected=[file for file in self.work['files'] if file.get('season')==season]
        if not selected:
            QMessageBox.information(self.window,'选择集','请先选中要移除的集，可使用 Ctrl / Shift 多选。');return
        return [file['id'] for file in selected]

    def remove_selected_episodes(self,whole_season=False):
        ids=self.selected_episode_ids(whole_season)
        if ids:self.remove_episode_records(ids)

    def delete_selected_episode_files(self,whole_season=False):
        ids=self.selected_episode_ids(whole_season)
        if ids:self.window.delete_work_files(self.work_id,ids)

    def remove_episode_records(self, file_ids):
        file_ids=[file['id'] for file in self.work['files'] if file['id'] in set(file_ids)]
        if not file_ids:return
        count=len(file_ids)
        names='\n'.join(Path(file['path']).name for file in self.work['files'] if file['id'] in file_ids)
        prompt=QMessageBox(self.window);prompt.setWindowTitle('移除季集记录')
        prompt.setText(f'将从媒体库移除 {count} 集，观看进度与书签一并清除；视频文件保留在磁盘，下次扫描可能重新入库。')
        prompt.setDetailedText(names);prompt.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)
        prompt.button(QMessageBox.StandardButton.Yes).setText('仅移除记录');prompt.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if prompt.exec()!=QMessageBox.StandardButton.Yes:return
        origin=self.work_id
        def apply(lib, progress):
            return lib.remove_local_records(origin,file_ids)
        def done(result):
            if result.get('removed_work'):self.window.back_details();self.window.refresh()
            elif self.window.detail_page is not None and self.window.detail_page.work_id==origin:self.window.reload_details(origin)
            self.window.status.setText(f"已移除 {result['removed']} 条季集记录，文件保留在磁盘")
        self.window.run_job('移除季集记录',apply,done)

    def recapture(self):
        if not self.work['files']:
            return
        f = self.files.currentItem().data(Qt.ItemDataRole.UserRole) if self.files.currentItem() else self.work['files'][0]
        second, ok = QInputDialog.getDouble(self, '选择封面画面', '截取时间（秒）', min(f['duration'] * .15, 300), 0, max(0, f['duration'] - .1), 1)
        if ok:
            def generate(lib, progress):
                target = lib.directory / 'cache' / (f['digest'] + '.jpg')
                thumbnail(f['path'], target, f['duration'], second)
                with lib.db:
                    lib.db.execute('UPDATE works SET thumbnail=? WHERE id=?', (str(target), self.work_id))
                    selected=lib.setting(f'artwork_{self.work_id}',{})
                    selected['thumbnail']=str(target)
                    lib.db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)',
                                   (f'artwork_{self.work_id}',json.dumps(selected,ensure_ascii=False)))
            self.window.run_job('重新截取封面', generate)
            self.accept()


class MainWindow(QMainWindow):
    shutdownFinished=Signal()
    # Production browsing always runs on a worker. GUI regression fixtures may
    # opt into deterministic small-catalog rendering without changing workers.
    synchronous_small_catalog = False
    def __init__(self, directory=None):
        super().__init__()
        self.library = Library(directory,timeout=.15)
        from .task_journal import TaskJournal,TaskBudget
        self.task_journal=TaskJournal(self.library.directory)
        self.task_budget=TaskBudget(self.library.setting('background_concurrency',1))
        self.lan_server = None
        self.setWindowTitle('Lumen · 私人光影库')
        self.resize(1400, 900)
        self.setMinimumSize(1024, 700)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        self._auxiliary_jobs=set()
        self.jobs = []
        self.job_queue=[];self.jobs_paused=False;self._job_resources={};self._job_functions={}
        self._closing = False
        self._browse_job=None;self._browse_pending=None;self._browse_epoch=0
        self.section, self.subtab = 'home', 0
        self.filters = {}
        self.current_items = []
        self.display_count = 0
        self.random_active = False
        self.navigation_history=[];self._restore_browse_state=None
        self.player = Player(self.library, self)
        self.player.queueNext.connect(lambda: self.step_playback(1))
        self.player.queuePrevious.connect(lambda: self.step_playback(-1))
        self.player.refreshed.connect(self.playback_refreshed)
        self.player.bookmarksChanged.connect(lambda:self.detail_page.refresh_bookmarks() if self.detail_page else None)
        from .remote import DesktopRemote
        self.remote=DesktopRemote(self)
        self.root = QWidget()
        self.root.setObjectName('root')
        self.setCentralWidget(self.root)
        root = QVBoxLayout(self.root)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        header.setFixedHeight(68)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 8, 26, 8)
        self.drawer = QScrollArea();self.drawer.setWidgetResizable(True);self.drawer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.drawer.setObjectName('sidebar');self.drawer.setFixedWidth(180)
        drawer_content=QWidget();self.drawer.setWidget(drawer_content)
        menu_button = button('☰', lambda: self.drawer.setVisible(not self.drawer.isVisible()))
        menu_button.setObjectName('headerButton')
        menu_button.setToolTip('媒体库与工具')
        header_layout.addWidget(menu_button)
        self.navigation_back=ActionButton('返回上一页','back',self.back_navigation).icon_only()
        self.navigation_back.hide();header_layout.addWidget(self.navigation_back)
        header_layout.addWidget(label('Lumen', 'brand'))
        header_layout.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索媒体库')
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(240)
        self.search.returnPressed.connect(self.search_all)
        header_layout.addWidget(self.search)
        for title,caption,symbol,callback in [('电脑播放队列','队列','play',self.show_queue),('任务中心','任务','check',self.show_tasks),('媒体管理','管理','folder',self.media_management)]:
            control=ActionButton(title,symbol,callback);control.setText(caption);control.setToolTip(title);header_layout.addWidget(control)
        header_layout.addWidget(ActionButton('设置','settings',self.settings).icon_only())
        root.addWidget(header)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(body, 1)
        nav = QVBoxLayout(drawer_content);nav.setContentsMargins(6,10,6,10);nav.setSpacing(2)
        self.nav_buttons = {}
        def nav_item(key,title,action):
            control=button(title,action);control.setObjectName('nav');control.setCheckable(True)
            control.setStyleSheet('padding: 8px 12px; text-align: left;');self.nav_buttons[key]=control;nav.addWidget(control)
        nav_item('home','首页',lambda:self.navigate('home'))
        nav.addWidget(label('媒体库','eyebrow'))
        for key,title in KINDS.items():nav_item(key,title,lambda checked=False,key=key:self.navigate(key))
        nav_item('actors','女演员',self.open_actresses)
        nav_item('discover','影片发现',lambda:self.navigate('discover'))
        nav.addWidget(label('我的','eyebrow'))
        nav_item('favorites','收藏',self.open_favorites)
        nav_item('watchlist','想看',self.open_watchlist)
        nav_item('lists','智能片单',self.load_list)
        nav_item('stats','历史与统计',lambda:self.navigate('stats'))
        nav.addStretch()
        nav.addWidget(label('管理','eyebrow'))
        nav.addWidget(button('媒体管理',self.media_management))
        nav.addWidget(button('任务中心',self.show_tasks))
        body.addWidget(self.drawer)
        self.pages = QStackedWidget()
        self.browse_page = QWidget()
        self.pages.addWidget(self.browse_page)
        self.detail_page = None
        self.details_scroll = None
        body.addWidget(self.pages, 1)
        main = QVBoxLayout(self.browse_page)
        main.setContentsMargins(24, 16, 24, 12)
        main.setSpacing(10)
        tools_row = QHBoxLayout()
        self.import_control = ActionButton('添加媒体','plus',self.import_dialog)
        self.filter_control = ActionButton('筛选','filter',self.filter_dialog)
        self.heading = label('', 'heading')
        tools_row.addWidget(self.heading)
        tools_row.addStretch()
        tools_row.addWidget(self.filter_control)
        tools_row.addWidget(ActionButton('媒体目录','folder',self.library_tools))
        tools_row.addWidget(self.import_control)
        main.addLayout(tools_row)
        self.subtitle = label('', 'subtitle')
        main.addWidget(self.subtitle)
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.currentChanged.connect(self.tab_changed)
        main.addWidget(self.tabs)
        self.filter_chips=QWidget();self.filter_flow=FlowLayout(self.filter_chips);main.addWidget(self.filter_chips)
        from .home import HomePage
        self.home_page = HomePage(self)
        self.home_page.hide()
        self.toolbar = FlowLayout(spacing=8)
        self.shuffle_action=ActionButton('随机播放','shuffle',self.shuffle);self.toolbar.addWidget(self.shuffle_action)
        lists=ActionButton('片单','bookmark');list_menu=QMenu(lists);list_menu.addAction('保存当前筛选为片单…',self.save_list);list_menu.addAction('打开片单…',self.load_list);lists.setMenu(list_menu);self.toolbar.addWidget(lists)
        self.toolbar.addWidget(button('打开智能片单', self.load_list))
        self.toolbar.addWidget(button('刷新新片', self.discover))
        self.view_mode = QComboBox()
        self.view_mode.addItem('海报', 'poster')
        self.view_mode.addItem('缩略图', 'thumbnail')
        self.view_mode.setCurrentIndex(max(0, self.view_mode.findData(self.library.setting('view_mode', 'poster'))))
        self.view_mode.currentIndexChanged.connect(self.change_view_mode)
        self.toolbar.addWidget(self.view_mode)
        self.list_more=ActionButton('更多','more');self.list_menu=QMenu(self.list_more);self.list_more.setMenu(self.list_menu)
        self.artwork_size_action=self.list_menu.addAction('全局显示大小…',self.choose_artwork_sizes)
        self.catalog_sort=QComboBox()
        for text,key in [('入库时间','added'),('名称','title'),('年份','year'),('个人评分','rating'),('时长','duration')]:self.catalog_sort.addItem(text,key)
        self.catalog_sort.setCurrentIndex(max(0,self.catalog_sort.findData(self.library.setting('catalog_sort','added'))))
        self.catalog_sort.currentIndexChanged.connect(self.change_catalog_sort);self.toolbar.addWidget(self.catalog_sort)
        self.catalog_direction=QPushButton('降序' if self.library.setting('catalog_descending',True) else '升序')
        self.catalog_direction.clicked.connect(self.flip_catalog_sort);self.toolbar.addWidget(self.catalog_direction)
        self.batch_select=QPushButton('多选');self.batch_select.setCheckable(True);self.batch_select.toggled.connect(self.select_catalog_mode);self.toolbar.addWidget(self.batch_select)
        from .catalog_ui import batch_menu,relocate
        self.batch_action=button('批量操作',lambda:batch_menu(self))
        self.relocate_action=self.list_menu.addAction('修复当前分类路径…',lambda:relocate(self))
        self.actor_min = QComboBox()
        for n in [0,1,3,5,10]:
            self.actor_min.addItem(f'至少 {n} 部已评分', n)
        self.actor_min.currentIndexChanged.connect(self.refresh)
        self.toolbar.addWidget(self.actor_min)
        self.actor_sort = QComboBox()
        for text, key in [('个人均分', 'average'),('影片数量','count'),('已评分数量','rated'),('姓名','name')]:
            self.actor_sort.addItem(text, key)
        self.actor_sort.currentIndexChanged.connect(self.refresh)
        self.toolbar.addWidget(self.actor_sort)
        self.actor_photo_action=button('刮削演员头像…',self.scrape_actor_photo)
        self.toolbar.addWidget(self.actor_photo_action)
        self.actor_batch_action=button('批量获取头像…',self.batch_actor_photos)
        self.toolbar.addWidget(self.actor_batch_action)
        self.toolbar.addWidget(self.list_more)
        self.source_filter = QComboBox()
        self.category_filter = QComboBox()
        self.category_filter.addItem('全部分类', '')
        from .discovery_ui import DiscoveryPanel
        self.discovery_panel=DiscoveryPanel(self)
        main.addWidget(self.discovery_panel)
        main.addLayout(self.toolbar)
        self.batch_bar=QWidget();batch_layout=FlowLayout(self.batch_bar,spacing=8)
        self.batch_count=label('已选 0 部');batch_layout.addWidget(self.batch_count);batch_layout.addWidget(self.batch_action)
        self.batch_export=button('导出选中影片 NFO…',self.export_selected_nfo);batch_layout.addWidget(self.batch_export)
        batch_layout.addWidget(button('退出多选',lambda:self.batch_select.setChecked(False)))
        self.batch_bar.hide();main.addWidget(self.batch_bar)
        main.addWidget(self.home_page, 1)
        self.splitter = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('文件夹')
        self.tree.itemClicked.connect(self.folder_selected)
        self.splitter.addWidget(self.tree)
        self.cards = PosterList(self.play_work)
        self.cards.favoriteRequested.connect(self.toggle_favorite)
        self.cards.actorPortraitDropped.connect(self.replace_actor_portrait)
        self.cards.watchlistRequested.connect(lambda work_id:self.toggle_card_personal(work_id,'watchlist'))
        self.cards.setObjectName('posters')
        self.cards.setViewMode(QListWidget.ViewMode.IconMode)
        self.cards.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.cards.setMovement(QListWidget.Movement.Static)
        self.cards.setSpacing(4)
        self.cards.setMouseTracking(True)
        self.cards.setUniformItemSizes(True)
        self.cards.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.cards.setItemDelegate(PosterDelegate(self.cards))
        self.cards.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cards.itemClicked.connect(self.open_item)
        self.cards.itemSelectionChanged.connect(self.update_batch_actions)
        self.cards.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cards.customContextMenuRequested.connect(self.card_menu)
        self.cards.verticalScrollBar().valueChanged.connect(self.load_more)
        from .discovery_images import DiscoveryImages
        self.discovery_images=DiscoveryImages(self)
        self.splitter.addWidget(self.cards)
        self.splitter.setSizes([220, 900])
        main.addWidget(self.splitter, 1)
        self.stats_scroll = QScrollArea()
        self.stats_scroll.setWidgetResizable(True)
        self.stats_widget = QWidget()
        self.stats_layout = QVBoxLayout(self.stats_widget)
        self.stats_scroll.setWidget(self.stats_widget)
        main.addWidget(self.stats_scroll, 1)
        self.empty = label('')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        main.addWidget(self.empty, 1)
        self.job_area=QWidget();self.job_area.setFixedHeight(40);self.job_area.hide()
        job_row=QHBoxLayout(self.job_area);job_row.setContentsMargins(42,0,42,0);job_row.setSpacing(12)
        self.job_progress = QProgressBar();self.job_progress.setFixedHeight(8);self.job_progress.setTextVisible(False);self.job_progress.setMinimumWidth(0)
        self.job_progress.hide()
        job_row.addWidget(self.job_progress,1)
        self.job_counter=ElidedLabel();self.job_counter.setFixedWidth(100);self.job_counter.hide();job_row.addWidget(self.job_counter)
        self.cancel_job = button('停止处理队列',self.stop_jobs)
        self.cancel_job.setFixedWidth(150);self.cancel_job.setStyleSheet('padding: 3px 10px; min-height: 22px;')
        self.cancel_job.hide()
        job_row.addWidget(self.cancel_job)
        root.addWidget(self.job_area)
        self.status = ElidedLabel('就绪');self.status.setObjectName('subtitle')
        self.status.setContentsMargins(42,0,42,0)
        root.addWidget(self.status)
        self.navigate('home')
        config = self.library.setting('lan', {})
        if config.get('enabled'):
            try:
                self.apply_lan(True, config.get('port',8097))
            except Exception as exc:
                self.status.setText('局域网服务未启动：' + str(exc))
        self.scheduler = QTimer(self)
        self.scheduler.setInterval(60_000)
        self.scheduler.timeout.connect(self.schedule_discovery)
        self.scheduler.start()
        self.media_scheduler = QTimer(self)
        self.media_scheduler.setInterval(1500)
        self.media_scheduler.timeout.connect(self.schedule_media)
        self.media_scheduler.start()
        QTimer.singleShot(4000, self.schedule_discovery)
        set_tool_directory(self.library.setting('ffmpeg_directory',''))
        self._fftools_prompted=False
        QTimer.singleShot(2500,self.check_fftools)
        self.inspect_scheduler=QTimer(self)
        self.inspect_scheduler.setInterval(30*60_000)
        self.inspect_scheduler.timeout.connect(self.schedule_inspect)
        self.inspect_scheduler.start()
        QTimer.singleShot(600_000,self.schedule_inspect)
        self.resource_scheduler=QTimer(self);self.resource_scheduler.setInterval(500);self.resource_scheduler.timeout.connect(self.sync_playback_budget);self.resource_scheduler.start()
        self.watch_scheduler=QTimer(self);self.watch_scheduler.setInterval(10000);self.watch_scheduler.timeout.connect(self.schedule_watched);self.watch_scheduler.start()
        with self.library.db:
            self.library.db.execute("UPDATE tasks SET status='cancelled',error='应用重启，未完成任务可重试' WHERE kind='background' AND status IN ('running','paused','queued')")

    def media_management(self,section=None):
        from .media_management_ui import show_media_management
        return show_media_management(self,section if isinstance(section,str) else None)

    def library_tools(self):
        return self.media_management('directories')

    def numbered_sources(self):
        from .numbered_sources_ui import show_numbered_providers
        return show_numbered_providers(self)

    def metadata_health(self):
        from .metadata_health_ui import show_metadata_health
        return show_metadata_health(self)

    def duplicate_versions(self):
        from .versions_ui import show_duplicates
        return show_duplicates(self)

    def compare_versions(self,work_ids):
        from .versions_ui import show_versions
        return show_versions(self,work_ids)

    def export_nfo(self,work_ids=None):
        from .nfo_export_ui import export_dialog
        if not isinstance(work_ids,list):
            if self.detail_page is not None:
                QMessageBox.information(self,'导出范围','请在影片详情的“资料与图片”中导出当前影片，或返回列表选择影片。');return
            selected=[item.data(Qt.ItemDataRole.UserRole) for item in self.cards.selectedItems()]
            records=selected if self.batch_select.isChecked() and selected else self.current_items
            work_ids=[item['id'] for item in records if item.get('kind') in {'movie','series','vr'}]
        if not work_ids:
            QMessageBox.information(self,'导出资料','请先进入影片列表或选择需要导出的影片。');return
        return export_dialog(self,work_ids)

    def playback_refreshed(self):
        self.refresh()
        if self.detail_page:self.detail_page.sync_personal();self.detail_page.refresh_bookmarks()

    def schedule_watched(self):
        if self.jobs or self.job_queue or self.jobs_paused or self._closing or self.task_budget.playback:return
        if not any(row.get('enabled', True) for row in self.library.setting('watched_folders', [])) and not self.library.db.execute("SELECT 1 FROM tasks WHERE kind='ingest' AND status IN ('queued','running','retry') LIMIT 1").fetchone():return
        from .media_tools import watch_folders
        def ingest(lib, progress):
            from .ingestion import process_pending
            watched = watch_folders(lib, progress, cancelled=progress.cancelled)
            watched['automation'] = process_pending(lib, progress, progress.cancelled)
            return watched
        self.run_job('目录监控与自动入库', ingest, quiet=True, background=True)

    def pause_jobs(self,paused):
        self.jobs_paused=paused
        self.task_budget.set_paused(paused)
        if self.lan_server:self.lan_server.downloads.pause(paused)
        for job in self.jobs:
            job.paused.set() if paused else job.paused.clear()
            identifier=getattr(job,'task_identifier',None)
            row=self.library.db.execute('SELECT payload FROM tasks WHERE id=?',(identifier,)).fetchone() if identifier else None
            if row:self.task_journal.record(identifier,'background','paused' if paused else 'running',json.loads(row['payload']))
        if not paused:self.start_queued_jobs()

    def sync_playback_budget(self):
        if self._closing:return
        playing=self.player.isVisible() and self.player.file is not None and self.player.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState
        if self.lan_server:
            now=self.lan_server.clock()
            playing=playing or any(state.get('playing') and now-state['time']<5 for state in tuple(self.lan_server.sessions.values()))
        changed=self.task_budget.playback!=bool(playing)
        self.task_budget.set_playback(playing)
        if changed:self.start_queued_jobs()

    def job_capacity_used(self):
        return sum(not (getattr(job,'background',False) and self.task_budget.playback) for job in self.jobs)

    def start_queued_jobs(self):
        if self._closing or self.jobs_paused:return
        limit=max(1,min(3,int(self.library.setting('background_concurrency',1))))
        self.job_queue.sort(key=lambda queued:self._job_resources.get(queued[3],('disk',False))[1])
        while self.job_queue and self.job_capacity_used()<limit:
            title,function,callback,identifier,quiet=self.job_queue[0]
            resource,background=self._job_resources.get(identifier,('disk',False))
            if background and self.task_budget.playback:break
            self.job_queue.pop(0)
            self.run_job(title,function,callback,_identifier=identifier,quiet=quiet,resource=resource,background=background)

    def schedule_media(self):
        if self.jobs or self.job_queue or self.jobs_paused or self._closing or self.task_budget.playback:
            return
        pending = self.library.db.execute('SELECT COUNT(*) FROM import_cache WHERE pending IN (1,2)').fetchone()[0]
        if pending:
            self.run_job(f'后台补充媒体信息 · 剩余 {pending} 个', lambda lib, progress: lib.enrich_pending(progress, cancelled=progress.cancelled), self.media_enrich_done, resource='cpu', background=True)

    def media_enrich_done(self, result):
        if isinstance(result, dict) and result.get('needs_ffmpeg'):
            self.status.setText('缺少 FFmpeg 组件：读取时长与缩略图已暂停；可在设置中配置目录或联网下载')
            self.schedule_fftools(force=True)

    def schedule_inspect(self):
        """One rotating batch per opportunity, at most every two hours; always yields to real work."""
        if self._closing or self.jobs or self.job_queue or self.jobs_paused:
            return
        state = self.library.setting('inspection', {})
        if state.get('last') and time.time() - state['last'] < 2 * 3600:
            return
        def run(lib, progress):
            return lib.inspect_batch(progress=progress, cancelled=progress.cancelled)
        def done(result):
            if not isinstance(result, dict) or result.get('cancelled'):return
            if result.get('missing') or result.get('imported') or result.get('renamed') or result.get('errors'):
                self.status.setText(f"媒体库巡检：缺失 {result['missing']} · 恢复重命名 {result['renamed']} · "
                                    f"新增 {result['imported']} · 失败 {result['errors']}；缺失详情见任务页")
        self.run_job('媒体库巡检（分批后台）', run, done, quiet=True, _identifier=INSPECT_JOB, background=True)

    def check_fftools(self):
        if self._closing or self._fftools_prompted or os.environ.get('LUMEN_SMOKE'):
            return
        from . import fftools
        if not fftools.needed():
            return
        self._fftools_prompted=True
        missing='、'.join(fftools.missing_tools())
        dialog=QDialog(self);dialog.setWindowTitle('FFmpeg 组件')
        layout=QVBoxLayout(dialog)
        message=label(f'未检测到 {missing}。读取时长和生成缩略图需要它们，视频播放不受影响。\n可以使用本机已有的 FFmpeg（选择其所在目录），或联网自动下载一次（约 110MB）。')
        message.setWordWrap(True);layout.addWidget(message)
        row=QHBoxLayout()
        row.addWidget(button('配置已有 FFmpeg 目录…',lambda:self.configure_fftools(dialog)))
        row.addWidget(button('联网自动下载',lambda:self.start_fftools_download(dialog)))
        row.addStretch();row.addWidget(button('暂不',dialog.accept))
        layout.addLayout(row)
        dialog.exec();dialog.deleteLater()

    def configure_fftools(self, parent=None):
        from .dialogs import existing_directory
        from . import fftools
        directory=existing_directory(self,'选择包含 ffmpeg.exe 和 ffprobe.exe 的目录')
        if not directory:
            return
        folder=Path(directory)
        missing=[name+'.exe' for name in fftools.TOOLS if not (folder/name).is_file()]
        if missing:
            QMessageBox.warning(self,'FFmpeg 目录','所选目录缺少：'+', '.join(missing));return
        self.library.set_setting('ffmpeg_directory',str(folder))
        set_tool_directory(str(folder))
        self.status.setText('FFmpeg 组件已就绪：'+str(folder))
        if parent is not None:parent.accept()

    def start_fftools_download(self, parent=None):
        if parent is not None:parent.accept()
        self.schedule_fftools(force=True)

    def schedule_fftools(self, force=False):
        if self._closing or self.jobs_paused:
            return
        from . import fftools
        if not fftools.needed():
            return
        busy=any(getattr(job,'task_identifier',None)==FFTOOLS_JOB for job in self.jobs) or any(queued[3]==FFTOOLS_JOB for queued in self.job_queue)
        if busy:
            return
        if (self.jobs or self.job_queue) and not force:
            QTimer.singleShot(60000,self.schedule_fftools)
            return
        def fetch(lib, progress):
            try:
                return fftools.ensure(progress, progress.cancelled, lib.setting('proxy') or None)
            except ImportCancelled:
                raise
            except Exception as error:
                return {'failed':str(error)}
        def done(result):
            if isinstance(result,dict) and result.get('failed'):
                self.status.setText('FFmpeg 组件未能下载：'+result['failed']+'；可在设置中配置本机 FFmpeg 目录')
            elif isinstance(result,dict) and result.get('ffmpeg'):
                self.status.setText('FFmpeg 组件已就绪：'+result['ffmpeg'])
        self.run_job('下载 FFmpeg 组件（仅一次）',fetch,done,_identifier=FFTOOLS_JOB)

    def open_favorites(self):
        self.navigate('home');self.tabs.setCurrentIndex(2);self.filters={'favorite':True};self.heading.setText('收藏');self.refresh();self.set_nav_selection('favorites')

    def open_watchlist(self):
        self.navigate('home');self.tabs.setCurrentIndex(3);self.heading.setText('想看');self.set_nav_selection('watchlist')

    def open_actresses(self):
        self.navigate('movie');self.tabs.setCurrentIndex(1);self.heading.setText('女演员');self.set_nav_selection('actors')

    def set_nav_selection(self,key):
        for name,control in self.nav_buttons.items():control.setChecked(name==key)

    def navigate(self, section, preserve_history=False):
        self._close_details()
        if not preserve_history:self.navigation_history.clear();self._restore_browse_state=None
        self.navigation_back.setVisible(bool(self.navigation_history))
        if self.batch_select.isChecked():self.batch_select.setChecked(False)
        self.section, self.subtab = section, 0
        self.filters = {}
        self.search.clear()
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        titles = {'home':['媒体总览','继续观看','最近入库','想看'], 'movie':['影片海报墙','女演员墙'], 'series':['剧集海报墙'],
                  'recommend':['为我推荐'], 'vr':['VR影片海报墙'], 'fans':['作者文件夹'], 'other':['文件夹浏览'], 'discover':['全部发现','网站最新收录','想看清单'], 'stats':['数据概览','日趋势','周趋势','月趋势','年度报告','影片偏好','评分分布','观看历史']}
        for text in titles[section]:
            self.tabs.addTab(text)
        self.tabs.blockSignals(False)
        self.heading.setText({'home':'首页','recommend':'为我推荐','movie':'电影','series':'电视剧','vr':'VR电影','fans':'Fans','other':'其他视频','discover':'影片发现','stats':'观影统计'}[section])
        self.set_nav_selection('home' if section=='recommend' else section)
        if section == 'discover':
            self.discovery_panel.reload_sources()
            self.discovery_panel.reset_view()
        else:self.discovery_panel.token+=1
        self.discovery_panel.setVisible(section=='discover')
        self.search.setVisible(section!='discover')
        self.refresh()

    def tab_changed(self, index):
        self.subtab = max(index, 0)
        if self.section=='discover' and index==1:
            self.discovery_panel.sort.blockSignals(True);self.discovery_panel.sort.setCurrentIndex(self.discovery_panel.sort.findData('site_added'));self.discovery_panel.sort.blockSignals(False)
            self.discovery_panel.change_sort(refresh=False)
        self.refresh()

    def effective_filters(self):
        filters = dict(self.filters)
        if self.section=='discover':
            filters.setdefault('sort',self.discovery_panel.sort.currentData())
            filters.setdefault('descending',self.discovery_panel.descending)
        else:
            filters.setdefault('sort',self.library.setting('catalog_sort','added'))
            filters.setdefault('descending',self.library.setting('catalog_descending',True))
        if self.section in KINDS:
            filters.setdefault('kinds', [self.section])
        if self.section == 'home' and self.subtab == 3:
            filters['watchlist'] = True
        if self.section == 'home' and self.subtab == 1:
            filters['continue'] = True
        if self.section == 'movie' and self.subtab == 1:
            filters['female_cast'] = True
        if self.search.text().strip() and not (self.section=='discover' and self.discovery_panel.online_results()):
            filters['query'] = self.search.text().strip()
        return filters

    def change_catalog_sort(self):
        self.library.set_setting('catalog_sort',self.catalog_sort.currentData());self.filters.pop('sort',None);self.refresh()

    def flip_catalog_sort(self):
        value=not self.effective_filters().get('descending',True);self.library.set_setting('catalog_descending',value)
        self.catalog_direction.setText('降序' if value else '升序');self.filters.pop('descending',None);self.refresh()

    def sync_catalog_sort(self):
        effective=self.effective_filters()
        self.catalog_sort.blockSignals(True)
        self.catalog_sort.setCurrentIndex(max(0,self.catalog_sort.findData(effective.get('sort','added'))))
        self.catalog_sort.blockSignals(False)
        self.catalog_direction.setText('降序' if effective.get('descending',True) else '升序')

    def select_catalog_mode(self,enabled):
        self.cards.setProperty('batchMode',enabled)
        self.cards.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection if enabled else QAbstractItemView.SelectionMode.SingleSelection)
        self.cards.clearSelection();self.update_batch_actions()

    def update_batch_actions(self):
        active=self.batch_select.isChecked() and self.batch_select.isVisible()
        count=len(self.cards.selectedItems());self.batch_bar.setVisible(active)
        self.batch_count.setText(f'已选 {count} 部');self.batch_action.setEnabled(count>0);self.batch_export.setEnabled(count>0)

    def export_selected_nfo(self):
        ids=[item.data(Qt.ItemDataRole.UserRole)['id'] for item in self.cards.selectedItems() if item.data(Qt.ItemDataRole.UserRole).get('kind') in {'movie','series','vr'}]
        if ids:self.export_nfo(ids)

    def change_view_mode(self):
        self.library.set_setting('view_mode', self.view_mode.currentData())
        if self.view_mode.currentData() == 'thumbnail':
            for file in self.library.db.execute('SELECT f.id,f.digest FROM files f JOIN import_cache c ON c.file_id=f.id WHERE c.pending=0').fetchall():
                if not (self.library.directory / 'cache' / (file['digest'] + '.jpg')).exists():
                    with self.library.db:
                        self.library.db.execute('UPDATE import_cache SET pending=2 WHERE file_id=?',(file['id'],))
        self.refresh()

    def choose_artwork_sizes(self):
        dialog=QDialog(self);dialog.setWindowTitle('显示大小 · 全局');layout=QFormLayout(dialog)
        poster=QSpinBox();poster.setRange(120,300);poster.setSuffix(' px');poster.setValue(self.library.setting('poster_width',190))
        thumb=QSpinBox();thumb.setRange(200,480);thumb.setSuffix(' px');thumb.setValue(self.library.setting('thumbnail_width',280))
        layout.addRow('海报卡片宽度（2:3）',poster);layout.addRow('缩略图卡片宽度（16:9）',thumb)
        layout.addRow(QLabel('应用于整个媒体库；详情封面会按可用空间缩小，保存后立即生效。'))
        reset=button('恢复默认大小',lambda:(poster.setValue(190),thumb.setValue(280)));layout.addRow(reset)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
        if dialog.exec():
            self.library.set_setting('poster_width',poster.value());self.library.set_setting('thumbnail_width',thumb.value())
            self.refresh();self.cards.doItemsLayout()
            if self.detail_page:self.reload_details(self.detail_page.work_id)
        dialog.deleteLater()

    def card_data(self, data, landscape=False):
        record = {key:data[key] for key in ('id','kind','title','name','year','thumbnail','photo_cache','average','count','rated','favorite','watchlist','rating','_subtitle','_resume','reasons') if key in data}
        if 'work_ids' in data:record['work_ids']=[]
        record['files']=[{key:file[key] for key in ('id','work_id','path','digest','duration','position','completed','season','episode') if key in file} for file in data.get('files',[])]
        record['sources']=[{'rating':source.get('rating')} for source in data.get('sources',[])]
        record['_landscape'] = bool(data.get('kind')) and (landscape or self.view_mode.currentData() == 'thumbnail')
        record['_card_width']=self.library.setting('thumbnail_width' if record['_landscape'] else 'poster_width',280 if record['_landscape'] else 190)
        if record['_landscape']:
            from .artwork import thumbnail_path
            record['_cover']=thumbnail_path(self.library,data)
        selected=self.library.setting(f'artwork_{data.get("id")}',{}) if data.get('kind') else {}
        custom=selected.get('thumbnail' if record['_landscape'] else 'poster')
        if custom and Path(custom).is_file():record['_cover']=custom
        return record

    def refresh(self, *_, _data=None):
        if self._closing:return
        self.render_filter_chips()
        request={'section':self.section,'tab':self.subtab,'filters':self.effective_filters(),
                 'actor_min':self.actor_min.currentData(),'actor_sort':self.actor_sort.currentData(),
                 'year':getattr(self,'report_year',__import__('datetime').datetime.now().year)}
        if self.section=='discover':request.update(self.discovery_panel.request_fields())
        if _data is None:
            self._browse_epoch+=1
            self.discovery_images.refresh_visible()
            if self._restore_browse_state is not None and self._restore_browse_state.get('_epoch')!=self._browse_epoch:self._restore_browse_state=None
            if (not self.synchronous_small_catalog or self.jobs or
                self.library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0]>=250 or
                self.library.db.execute('SELECT COUNT(*) FROM files').fetchone()[0]>=1000):
                self._browse_pending=(self._browse_epoch,request)
                self.shuffle_action.setEnabled(False)
                self.subtitle.setText('正在后台读取媒体库…')
                if not self.jobs:self.status.setText('正在后台读取媒体库，页面仍可操作…')
                self._start_browse_read()
                return
            self._browse_pending=None
            from .browse import load_view
            _data=load_view(self.library,request)
        updates=self.browse_page.updatesEnabled()
        self.cards.setEnabled(True);self.home_page.setEnabled(True)
        if updates:self.browse_page.setUpdatesEnabled(False)
        try:self.render_browse_data(_data)
        finally:
            if updates:self.browse_page.setUpdatesEnabled(True)
        state=self._restore_browse_state
        if state is not None:
            self._restore_browse_state=None
            while self.display_count<min(state['display_count'],len(self.current_items)):self.append_cards()
            epoch=self._browse_epoch
            QTimer.singleShot(0,lambda:self.cards.verticalScrollBar().setValue(state['scroll']) if not self._closing and epoch==self._browse_epoch else None)
            QTimer.singleShot(0,lambda:self.home_page.verticalScrollBar().setValue(state['home_scroll']) if not self._closing and epoch==self._browse_epoch else None)

    def render_browse_data(self,_data):
        self.sync_catalog_sort()
        actresses = self.section == 'movie' and self.subtab == 1
        home=self.section=='home' and self.subtab==0
        for index in range(4):
            self.toolbar.itemAt(index).widget().setVisible((self.section == 'discover') if index == 3 else index!=2 and self.section not in {'discover','stats'})
        self.shuffle_action.setVisible(not actresses and self.section not in {'discover','stats'} and not home)
        self.view_mode.setVisible(not actresses and self.section != 'stats' and not home)
        self.artwork_size_action.setVisible(not actresses and self.section != 'stats')
        self.list_more.setVisible(not actresses and self.section!='stats' and not home)
        self.tabs.setVisible(self.tabs.count()>1)
        for control in [self.catalog_sort,self.catalog_direction]:control.setVisible(not actresses and self.section not in {'stats','discover','recommend'} and not home)
        self.batch_select.setVisible(not actresses and self.section not in {'stats','discover'} and not home)
        self.update_batch_actions()
        self.relocate_action.setVisible(self.section in KINDS)
        self.actor_min.setVisible(actresses)
        self.actor_sort.setVisible(actresses)
        self.actor_photo_action.setVisible(actresses)
        self.actor_batch_action.setVisible(actresses)
        self.cards.setProperty('actorPortraitDrop',actresses)
        self.cards.setAcceptDrops(True);self.cards.viewport().setAcceptDrops(True)
        self.source_filter.setVisible(self.section == 'discover')
        self.category_filter.setVisible(self.section == 'discover')
        self.discovery_panel.setVisible(self.section=='discover')
        self.tree.setVisible(self.section == 'other')
        self.stats_scroll.setVisible(self.section == 'stats')
        self.home_page.setVisible(home)
        self.subtitle.setVisible(not home)
        if home:
            self.splitter.hide()
            self.empty.hide()
            self.subtitle.hide()
            for index in range(4):
                self.toolbar.itemAt(index).widget().hide()
            self.home_page.refresh(_data['home'],_data['recommendations'])
            self.current_items = _data['recommendations']
            return
        if self.section == 'stats':
            self.splitter.hide()
            self.render_stats(_data['stats'],_data.get('report'),_data.get('history'))
            self.empty.hide()
            return
        if actresses:
            items = _data['items']
            for a in items:
                average = f"{a['average']:.1f} 分" if a['average'] is not None else '暂无个人评分'
                a['_subtitle'] = f"{average} · {a['count']} 部 / 已评分 {a['rated']}"
        elif self.section == 'home' and self.subtab == 0:
            items = self.library.recommendations()
        elif self.section == 'discover':
            items = _data['items']
            self.discovery_panel.set_facets(_data.get('facets',{}))
            for w in items:
                source=next(iter(w['sources']),{})
                w['_subtitle'] = ('已入库' if w['files'] else '未入库') + ' · ' + (source.get('site_added') or w['discovered'] or '')[:10]
        else:
            items = _data['items']
            if self.section=='other':self.build_tree(_data.get('tree'))
            if self.section == 'home' and self.subtab == 1:
                items = [w for w in items if w.get('_resume')]
            elif self.section == 'home' and self.subtab == 3:
                items = [w for w in items if w['watchlist']]
        view_key=json.dumps([self.section,self.subtab,self.effective_filters(),self.discovery_panel.request_fields() if self.section=='discover' else {},self.actor_min.currentData(),self.actor_sort.currentData(),self.view_mode.currentData()],sort_keys=True,ensure_ascii=False)
        preserve=view_key==getattr(self,'_rendered_view_key',None);self._rendered_view_key=view_key
        self.current_items = items
        self.shuffle_action.setEnabled(any(item.get('id') is not None and item.get('files') for item in items))
        count=min(len(items),max(60,self.display_count) if preserve else 60)
        update_poster_items(self.cards,[self.card_data(item) for item in items[:count]],preserve)
        self.display_count=self.cards.count()
        self.subtitle.setText(f"{len(items)} {'位女演员' if actresses else '部作品'}  ·  " + ('拖入图片到演员卡片可替换头像 · 未评分不计入均分' if actresses else '点击查看详情 · 右键快速播放'))
        self.empty.setText('这里还没有内容\n\n拖入真实视频文件夹，或点击“导入文件夹”开始。\n影片发现需先在设置中安装并配置插件。' if not items else '')
        self.empty.setVisible(not items)
        self.splitter.setVisible(bool(items))
        self.discovery_images.refresh_visible()

    def _start_browse_read(self):
        if self._browse_job is not None or self._browse_pending is None or self._closing:return
        from .browse import BrowseRead
        epoch,request=self._browse_pending;self._browse_pending=None
        job=BrowseRead(self.library.directory,request,self);self._browse_job=job
        outcome={}
        job.done.connect(lambda data:outcome.update(data=data))
        job.failed.connect(lambda error:outcome.update(error=error))
        def complete():
            self._browse_job=None;job.deleteLater()
            if self._closing:
                if not self.jobs:QTimer.singleShot(0,self.close)
                return
            if epoch==self._browse_epoch:
                if 'data' in outcome:
                    self.refresh(_data=outcome['data'])
                    if self.status.text().startswith('正在后台读取媒体库'):self.status.setText('就绪')
                else:
                    self.status.setText('读取媒体库失败：'+outcome.get('error','未知错误'))
                    self.cards.setEnabled(True);self.home_page.setEnabled(True)
            self._start_browse_read()
        job.finished.connect(complete);job.start()

    def append_cards(self):
        for data in self.current_items[self.display_count:self.display_count + 60]:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, self.card_data(data))
            item.setToolTip((data.get('title') or data.get('name', '')) + '\n' + '\n'.join(data.get('reasons', [])))
            self.cards.addItem(item)
        self.display_count = self.cards.count()
        self.discovery_images.refresh_visible()

    def load_more(self, value):
        if value >= self.cards.verticalScrollBar().maximum() - 200 and self.display_count < len(self.current_items):
            self.append_cards()
        self.discovery_images.refresh_visible()

    def open_item(self, item):
        if self.cards.property('batchMode'):return
        data = item.data(Qt.ItemDataRole.UserRole)
        if 'work_ids' in data:
            self.search_metadata('actor', data['name'])
        else:
            self.open_details(data['id'])

    def open_details(self, work_id, fetch=True, remember=True):
        if remember and (self.detail_page is None or self.detail_page.work_id!=work_id):self._remember_navigation()
        self._close_details()
        self.detail_page = Details(self, work_id)
        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setWidget(self.detail_page)
        self.pages.addWidget(self.details_scroll)
        self.pages.setCurrentWidget(self.details_scroll)
        if fetch:
            QTimer.singleShot(0,lambda:self.refresh_source_details(work_id,automatic=True))

    def reload_details(self, work_id):
        if self.detail_page is not None and self.detail_page.work_id == work_id:
            position = self.details_scroll.verticalScrollBar().value()
            self.open_details(work_id, fetch=False, remember=False)
            QTimer.singleShot(0, lambda: self.details_scroll.verticalScrollBar().setValue(position)
                              if self.detail_page is not None and self.detail_page.work_id == work_id else None)

    def refresh_source_details(self, work_id, automatic=False):
        if self._closing or self.detail_page is None or self.detail_page.work_id!=work_id:
            return
        from .artwork import detail_sources
        sources=detail_sources(self.library,work_id)
        if not sources:
            if not automatic:self.detail_page.gallery_status.setText('没有可用的详情插件。请安装并启用此影片来源对应、支持 detail 的插件。')
            return
        stamp=self.library.setting('detail_refresh:'+str(work_id),0)
        if automatic and time.time()-stamp<3600:
            return
        if any(job.isRunning() for job in self.jobs):
            if not automatic:self.detail_page.gallery_status.setText('当前后台任务尚未结束，请稍后刷新。')
            return
        self.detail_page.gallery_status.setText('正在加载来源详情、剧照与下载资源…')
        self.library.set_setting('detail_refresh:'+str(work_id),time.time())
        def fetch(library,progress):
            from .artwork import refresh_details
            return refresh_details(library,work_id,progress)
        def complete(result):
            if self.detail_page is not None and self.detail_page.work_id==work_id:
                position=self.details_scroll.verticalScrollBar().value()
                self.open_details(work_id,fetch=False,remember=False)
                self.details_scroll.verticalScrollBar().setValue(position)
                if result.get('errors'):self.detail_page.gallery_status.setText('部分来源未能更新：'+'；'.join(result['errors']))
        self.run_job('加载剧照与下载资源',fetch,complete)

    def _close_details(self):
        if self.details_scroll is not None:
            self.pages.setCurrentWidget(self.browse_page)
            self.pages.removeWidget(self.details_scroll)
            self.details_scroll.deleteLater()
            self.details_scroll = None
            self.detail_page = None

    def _remember_navigation(self):
        self.navigation_history.append({'section':self.section,'subtab':self.subtab,'filters':json.loads(json.dumps(self.filters)),
            'search':self.search.text(),'heading':self.heading.text(),'display_count':self.display_count,
            'nav':next((name for name,control in self.nav_buttons.items() if control.isChecked()),self.section),
            'scroll':self.cards.verticalScrollBar().value(),'home_scroll':self.home_page.verticalScrollBar().value(),
            'detail':self.detail_page.work_id if self.detail_page is not None else None,
            'detail_scroll':self.details_scroll.verticalScrollBar().value() if self.details_scroll is not None else 0,
            'source':self.source_filter.currentData(),'category':self.category_filter.currentData(),
            'discovery':self.discovery_panel.snapshot(),
            'actor_min':self.actor_min.currentIndex(),'actor_sort':self.actor_sort.currentIndex()})
        # Keep data-only history bounded; no hidden pages or image widgets remain alive.
        del self.navigation_history[:-30]
        self.navigation_back.show()

    def back_navigation(self):
        if not self.navigation_history:
            self._close_details();return
        state=self.navigation_history.pop()
        # A normal detail -> list return keeps the actual poster widgets and selection.
        same=(self.section==state['section'] and self.subtab==state['subtab'] and self.filters==state['filters'] and self.search.text()==state['search'])
        if self.section=='discover':same=same and self.discovery_panel.snapshot()==state.get('discovery') and self.source_filter.currentData()==state['source'] and self.category_filter.currentData()==state['category']
        self._close_details()
        if not same:
            self.navigate(state['section'],preserve_history=True)
            self.tabs.blockSignals(True);self.tabs.setCurrentIndex(state['subtab']);self.tabs.blockSignals(False)
            self.subtab=state['subtab'];self.filters=state['filters'];self.search.setText(state['search'])
            for control,key in [(self.source_filter,'source'),(self.category_filter,'category')]:
                control.blockSignals(True);control.setCurrentIndex(max(0,control.findData(state[key])));control.blockSignals(False)
            for control,key in [(self.actor_min,'actor_min'),(self.actor_sort,'actor_sort')]:
                control.blockSignals(True);control.setCurrentIndex(state[key]);control.blockSignals(False)
            if state['section']=='discover':self.discovery_panel.restore(state.get('discovery',{}))
            state['_epoch']=self._browse_epoch+1;self._restore_browse_state=state;self.refresh()
        self.heading.setText(state['heading']);self.set_nav_selection(state.get('nav',state['section']))
        if state['detail'] is not None:
            self.open_details(state['detail'],fetch=False,remember=False)
            scroll=self.details_scroll
            QTimer.singleShot(0,lambda:scroll.verticalScrollBar().setValue(state['detail_scroll']) if self.details_scroll is scroll else None)
        self.navigation_back.setVisible(bool(self.navigation_history))

    def back_details(self):
        if self.detail_page is not None:self.back_navigation()

    def search_metadata(self, field, value):
        discovered=self.section=='discover'
        self._remember_navigation()
        self.navigate('discover' if discovered else 'home',preserve_history=True)
        self.tabs.setCurrentIndex(1 if discovered else 2)
        if discovered:
            self.source_filter.blockSignals(True);self.source_filter.setCurrentIndex(0);self.source_filter.blockSignals(False)
            self.category_filter.blockSignals(True);self.category_filter.setCurrentIndex(0);self.category_filter.blockSignals(False)
        self.filters = {field: [value] if field == 'tags_all' else value}
        self.heading.setText(('标签：' if field == 'tags_all' else '演员：') + value)
        self.refresh()

    def reveal_file_path(self,path):
        from .file_location import reveal_video
        try:return reveal_video(path)
        except (OSError,ValueError) as error:QMessageBox.warning(self,'定位视频文件',str(error))

    def reveal_work_file(self,work_id):
        files=self.library.work(work_id).get('files',[])
        if not files:
            QMessageBox.information(self,'定位视频文件','此影片还没有本地视频文件。');return
        index=0
        if len(files)>1:
            labels=[str(file['path']) for file in files]
            selected,accepted=QInputDialog.getItem(self,'定位视频文件','选择要在文件管理器中显示的视频',labels,0,False)
            if not accepted:return
            index=labels.index(selected)
        return self.reveal_file_path(files[index]['path'])

    def card_menu(self, position, cards=None):
        source=cards if cards is not None else self.cards
        item = source.itemAt(position)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        if 'work_ids' in data:
            from .actor_ui import show_actor_scraper
            menu.addAction('刮削演员头像…',lambda:show_actor_scraper(self,data['name']))
            actor=next((actor for actor in self.current_items if actor.get('name')==data['name']),{})
            credits=[str(actor[key]) for key in ('photo_attribution','photo_license','photo_page','photo_source_url') if actor.get(key)]
            if credits:menu.addAction('头像来源 / 许可…',lambda:QMessageBox.information(self,'头像来源 / 许可','\n'.join(dict.fromkeys(credits))))
        menu.addAction('查看详情', lambda: self.open_item(item))
        if data.get('kind') and data['kind']!='fans':menu.addAction('从本地 NFO 补充图片…',lambda:self.import_nfo_artwork(data['id']))
        if data.get('kind'):
            menu.addAction('取消收藏' if data.get('favorite') else '收藏', lambda: self.toggle_favorite(data['id']))
        if data.get('files'):
            menu.addAction('播放 / 继续观看', lambda: self.play_work(data['id']))
            menu.addAction('在系统文件夹中显示…',lambda:self.reveal_work_file(data['id']))
        if data.get('kind') in {'movie', 'vr'}:
            target = 'movie' if data['kind'] == 'vr' else 'vr'
            menu.addAction('移至' + KINDS[target], lambda: self.change_movie_kind(data['id'], target))
        if data.get('kind'):
            menu.addAction('标记已看',lambda:self.catalog_watch(data['id'],'completed'))
            menu.addAction('标记未看 / 重置进度',lambda:self.catalog_watch(data['id'],'unwatched'))
            menu.addAction('从头播放',lambda:self.catalog_restart(data['id']))
            menu.addAction('加入电脑播放队列',lambda:self.library.edit_queue([*self.library.setting('queue',{'ids':[]})['ids'],data['id']]))
            menu.addAction('仅移出媒体库…',lambda:self.remove_catalog_work(data['id']))
            if data.get('files'):menu.addAction('删除本地文件…',lambda:self.delete_work_files(data['id']))
        menu.exec(source.mapToGlobal(position))

    def scrape_actor_photo(self):
        item=self.cards.currentItem();record=item.data(Qt.ItemDataRole.UserRole) if item else {}
        from .actor_ui import show_actor_scraper
        show_actor_scraper(self,record.get('name',''))

    def batch_actor_photos(self):
        from .actor_batch_ui import show_actor_batch
        return show_actor_batch(self)

    def replace_actor_portrait(self,record,path):
        actor=next((dict(item) for item in self.current_items if item.get('name')==record.get('name')
                    and item.get('id')==record.get('id') and 'work_ids' in item),None)
        if actor is None:
            self.status.setText('演员列表已变化，请刷新后重新拖入图片');return
        from .actor_portrait import replace_local_portrait
        def saved(result):
            self.status.setText(f"已替换 {result['name']} 的头像 · 同步 {result['updated']} 部作品")
            if self.detail_page:self.reload_details(self.detail_page.work_id)
        self.run_job('替换演员头像',lambda library,progress:replace_local_portrait(library,actor,path,cancelled=progress.cancelled),saved)

    def catalog_watch(self,work_id,state,file_id=None):
        self.library.set_watched(work_id,state,file_id);self.refresh()

    def catalog_restart(self,work_id):
        file=self.library.resume_file(work_id);self.library.set_watched(work_id,'reset',file['id']);file['position']=0;self.play_file(file)

    def remove_catalog_work(self,work_id):
        if QMessageBox.question(self,'仅移出媒体库','移除该条目及其观看记录、书签？原始视频和 NFO 文件保留；再次扫描可能重新入库。')!=QMessageBox.StandardButton.Yes:return
        if self.player.file and self.player.file['work_id']==work_id:self.player.finish();self.player.hide()
        try:self.library.remove_catalog(work_id)
        except Exception as error:QMessageBox.warning(self,'未移除',str(error));return
        self.back_details();self.refresh()

    def delete_work_files(self, work_id, file_ids=None):
        from .files import plan_delete
        try:
            plan = plan_delete(self.library, work_id,file_ids=file_ids)
        except Exception as error:
            QMessageBox.warning(self, '无法删除', str(error)); return
        size = f"（共 {plan['bytes'] / 1073741824:.2f} GB）" if plan['known_size'] else ''
        dialog = QMessageBox(self)
        dialog.setWindowTitle('删除本地文件')
        scope='并把该条目移出媒体库' if file_ids is None else '并移除所选季集的媒体库记录，其他季集保留'
        dialog.setText(f"将永久删除 {len(plan['paths'])} 个视频及同名字幕 / NFO / 图片{size}，{scope}。\n此操作不经过回收站，无法恢复。")
        dialog.setDetailedText('\n'.join(plan['paths']))
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Ok).setText('永久删除')
        dialog.button(QMessageBox.StandardButton.Cancel).setText('取消')
        if dialog.exec() != QMessageBox.StandardButton.Ok:return
        if self.player.file and self.player.file['work_id']==work_id and (file_ids is None or self.player.file['id'] in file_ids):self.player.finish();self.player.hide()
        from .files import execute_delete
        def done(result):
            self.status.setText(f"已删除 {result['deleted']} 个文件并移出媒体库")
            if file_ids is None or result.get('removed_work'):self.back_details()
            elif self.detail_page is not None and self.detail_page.work_id==work_id:self.reload_details(work_id)
            self.refresh()
        self.run_job('删除本地文件', lambda lib, progress: execute_delete(lib, work_id, progress, progress.cancelled,file_ids=file_ids), done)

    def change_movie_kind(self, work_id, kind):
        try:
            self.library.set_movie_kind(work_id, kind)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, '分类未更改', str(exc))

    def toggle_favorite(self,work_id):
        self.toggle_card_personal(work_id,'favorite')

    def toggle_card_personal(self,work_id,field):
        work=self.library.work(work_id);value=not bool(work[field])
        try:self.library.update_personal(work_id,**{field:value})
        except Exception as error:QMessageBox.warning(self,'未保存',str(error));return
        for record in self.current_items:
            if record.get('id')==work_id and record.get('kind'):record[field]=int(value)
        remove=(field=='favorite' and self.effective_filters().get('favorite') or field=='watchlist' and self.effective_filters().get('watchlist')) and not value
        for cards in self.findChildren(PosterList):
            for index in range(cards.count()-1,-1,-1):
                item=cards.item(index);record=item.data(Qt.ItemDataRole.UserRole) or {}
                if record.get('id')!=work_id or not record.get('kind'):continue
                if remove and cards is self.cards:cards.takeItem(index);self.display_count-=1
                else:record[field]=int(value);item.setData(Qt.ItemDataRole.UserRole,record)
        if remove:
            self.current_items=[item for item in self.current_items if item.get('id')!=work_id]
            self.subtitle.setText(f'{len(self.current_items)} 部作品');self.empty.setText('暂无符合条件的作品，可调整筛选。');self.empty.setVisible(not self.current_items)
        name='收藏' if field=='favorite' else '想看'
        self.status.setText(('已加入' if value else '已移出')+name+' · '+work['title'])

    def search_all(self):
        query = self.search.text()
        if self.section=='discover':
            self.discovery_panel.name.setText(query);self.discovery_panel.apply_local();return
        if self.section=='stats':self.navigate('home');self.tabs.setCurrentIndex(2)
        elif self.section=='home' and self.subtab==0:self.tabs.setCurrentIndex(2)
        self._close_details()
        self.search.setText(query)
        self.refresh()

    def render_filter_chips(self):
        filters=self.effective_filters()
        if 'kinds' not in self.filters:filters.pop('kinds',None)
        tokens=filter_tokens(filters)
        signature=json.dumps([tokens,self.section=='stats'],ensure_ascii=False,sort_keys=True)
        if signature==getattr(self,'_filter_chip_signature',None):return
        self._filter_chip_signature=signature;clear(self.filter_flow)
        for key,value,text in tokens:self.filter_flow.addWidget(chip(text,lambda checked=False,key=key,value=value:self.remove_filter(key,value),True))
        if tokens:self.filter_flow.addWidget(ActionButton('清空筛选','close',self.clear_filters))
        self.filter_chips.setVisible(bool(tokens) and self.section!='stats')
        self.filter_control.setText('筛选'+(f' · {len(tokens)}' if tokens else ''))
        self.filter_control.setIcon(icon('filter','#75d5ef' if tokens else '#dedee3'))

    def remove_filter(self,key,value=None):
        if key=='years':self.filters.pop('year_min',None);self.filters.pop('year_max',None)
        elif key.startswith('tags_'):
            self.filters[key]=[tag for tag in self.filters.get(key,[]) if tag!=value]
            if not self.filters[key]:self.filters.pop(key,None)
        else:
            self.filters.pop(key,None)
            if key=='query':
                self.search.clear()
                if self.section=='discover':self.discovery_panel.name.clear()
            if key=='watchlist' and self.section=='home' and self.subtab==3:self.tabs.setCurrentIndex(2)
        if self.section=='home' and self.subtab==2:self.heading.setText('媒体库')
        self.refresh()

    def clear_filters(self):
        if self.section=='discover':self.discovery_panel.clear();return
        self.filters={};self.search.clear()
        if self.section=='home' and self.subtab in {1,3}:self.tabs.setCurrentIndex(2)
        self.refresh()

    def filter_dialog(self):
        existing=getattr(self,'_filter_dialog',None)
        if existing is not None:existing.raise_();existing.activateWindow();return
        from .background import run_background
        continuing_scope=self.section=='home' and self.subtab==1
        dialog=FilterDialog(self.effective_filters(),self);self._filter_dialog=dialog
        dialog.facet_status.setText('正在读取下拉选项，可直接输入条件…');dialog.facet_status.show()
        local=self.section!='discover';alive=[True]
        def read(job):
            library=Library(self.library.directory,initialize=False)
            try:return library.filter_options(local=local)
            finally:library.close()
        def loaded(options):
            if alive[0] and not self._closing:dialog.set_options(options)
        def failed(error):
            if alive[0] and not self._closing:dialog.facet_status.setText('下拉选项读取失败，可手动输入：'+error)
        def finished(result):
            alive[0]=False
            # A completed facet worker has already scheduled its QObject for
            # deletion; only cancel workers still owned by the job registry.
            if job in self._auxiliary_jobs:job.requestInterruption()
            self._filter_dialog=None
            if result==QDialog.DialogCode.Accepted and not self._closing:
                filters=dialog.filters()
                if continuing_scope:
                    self.navigate('home');self.subtab=1;self.tabs.setCurrentIndex(1);self.heading.setText('继续观看')
                elif self.section not in {'discover','recommend'}:
                    self.navigate('home');self.subtab=2;self.tabs.setCurrentIndex(2);self.heading.setText('媒体库')
                self.filters=filters;self.search.setText(filters.get('query',''))
                if self.section=='discover':self.discovery_panel.sync_advanced_filters()
                self.refresh()
            dialog.deleteLater()
        job=run_background(self,read,loaded,failed);dialog.finished.connect(finished);dialog.open()

    def save_list(self):
        name, ok = QInputDialog.getText(self, '保存智能片单', '片单名称')
        if ok and name.strip():
            with self.library.db:
                self.library.db.execute('INSERT OR REPLACE INTO lists VALUES (?,?)', (name.strip(), json.dumps(self.effective_filters(), ensure_ascii=False)))
            self.status.setText('智能片单已保存')

    def load_list(self):
        dialog=QDialog(self);dialog.setWindowTitle('智能片单');dialog.resize(560,420)
        layout=QVBoxLayout(dialog);note=label('片单保存筛选条件，媒体库更新后会自动显示符合条件的影片。');note.setWordWrap(True);layout.addWidget(note)
        choices=QListWidget();choices.setObjectName('smartListChoices');layout.addWidget(choices,1)
        state=label('');state.setWordWrap(True);layout.addWidget(state)
        row=FlowLayout(spacing=8);layout.addLayout(row)
        opening=button('打开选中片单',lambda:None);opening.setObjectName('openSmartList');row.addWidget(opening)
        save=button('保存当前列表为片单…',lambda:None);row.addWidget(save)
        remove=button('删除选中片单',lambda:None);row.addWidget(remove)
        save.setEnabled(self.detail_page is None and self.section not in {'stats'} and not (self.section=='movie' and self.subtab==1))
        if not save.isEnabled():save.setToolTip('请先返回影片列表并设置筛选条件。')
        def reload():
            choices.clear()
            for name,filters in self.library.db.execute('SELECT name,filters FROM lists ORDER BY name COLLATE NOCASE'):
                item=QListWidgetItem(name);item.setData(Qt.ItemDataRole.UserRole,filters);choices.addItem(item)
            if choices.count():choices.setCurrentRow(0)
            state.setText('选择片单打开；删除片单不会删除影片。' if choices.count() else '尚无片单。可返回影片列表设置筛选，再保存为片单。')
            opening.setEnabled(bool(choices.count()));remove.setEnabled(bool(choices.count()))
        def open_selected():
            item=choices.currentItem()
            if not item:return
            name=item.text();filters=json.loads(item.data(Qt.ItemDataRole.UserRole));dialog.accept()
            self.navigate('home');self.tabs.setCurrentIndex(2);self.filters=filters;self.search.setText(filters.get('query',''))
            self.heading.setText('片单 · '+name);self.set_nav_selection('lists');self.refresh()
        def save_current():self.save_list();reload()
        def delete_selected():
            item=choices.currentItem()
            if item and QMessageBox.question(dialog,'删除智能片单','仅删除片单“'+item.text()+'”，影片及观看记录保留。是否继续？')==QMessageBox.StandardButton.Yes:
                with self.library.db:self.library.db.execute('DELETE FROM lists WHERE name=?',(item.text(),))
                reload()
        opening.clicked.connect(open_selected);choices.itemDoubleClicked.connect(lambda _:open_selected())
        save.clicked.connect(save_current);remove.clicked.connect(delete_selected)
        layout.addWidget(button('关闭',dialog.reject));reload();dialog.exec();dialog.deleteLater()

    def import_nfo_artwork(self, work_id=None):
        from .dialogs import existing_directory
        dialog=QDialog(self);dialog.setWindowTitle('从资源目录的 NFO 补充图片');dialog.resize(650,260)
        form=QFormLayout(dialog)
        current=self.library.work(work_id) if work_id else None
        initial=str(Path(current['files'][0]['path']).parent) if current and current['files'] else self.library.setting('artwork_folder','')
        path=QLineEdit(initial)
        browse=button('选择目录…',lambda:path.setText(existing_directory(dialog,'选择包含 NFO 和图片的资源目录',path.text()) or path.text()))
        row=QHBoxLayout();row.addWidget(path,1);row.addWidget(browse);form.addRow('资源目录',row)
        mode=QComboBox();mode.addItem('仅补充缺失：保留已有图片与锁定字段','missing');mode.addItem('强制覆盖：用 NFO 图片替换已有图片（包括图片锁定）','overwrite');form.addRow('更新方式',mode)
        message=label('更新海报、缩略图、背景图及剧照。只调整缓存图片关联；不改影片资料、评分、收藏或播放进度。原始文件保留。')
        message.setWordWrap(True);form.addRow(message)
        form.addRow(label('范围：'+current['title'] if current else '范围：所选目录下所有已入库作品'))
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);form.addRow(controls)
        controls.accepted.connect(dialog.accept);controls.rejected.connect(dialog.reject)
        if not dialog.exec():return
        directory=path.text().strip();selected=mode.currentData()
        if not Path(directory).is_dir():QMessageBox.information(self,'资源目录','请选择有效的资源目录。');return
        self.library.set_setting('artwork_folder',directory)
        def update(library,progress):
            from .local_artwork import refresh_local_artwork
            return refresh_local_artwork(library,directory,selected,work_id,progress,progress.cancelled)
        def complete(result):
            if work_id and self.detail_page is not None and self.detail_page.work_id==work_id:self.open_details(work_id,fetch=False)
            self.status.setText(f"本地图片更新：{result['works']} 部 · 海报 {result['poster']} · 缩略图 {result['thumbnail']} · 剧照 {result['stills']} · 跳过 {result['skipped']} · 警告 {len(result['warnings'])}")
            if result['warnings']:
                report=QMessageBox(self);report.setWindowTitle('部分图片未载入');report.setText('已完成其他图片更新，以下图片未能载入。')
                report.setDetailedText('\n'.join(item['path']+'：'+item['reason'] for item in result['warnings']));report.exec()
        self.run_job('本地 NFO 图片补充',update,complete)

    def import_dialog(self):
        self.import_path()

    def import_path(self, path=None, pending=None):
        if self._closing:return
        from .import_ui import ImportDialog
        dialog=getattr(self,'import_form',None)
        if dialog is None:dialog=self.import_form=ImportDialog(self)
        if dialog.isVisible() and path:
            dialog.add_folders([str(path),*map(str,pending or [])]);path=None
        elif not dialog.isVisible():dialog.pending=list(pending or [])
        dialog.refresh_scrapers()
        if path:dialog.path.setText(str(path))
        # A minimized or buried dialog makes drops look dead; restore and force it forward.
        already=dialog.isVisible()
        if dialog.isMinimized():dialog.showNormal()
        if not already:
            dialog.kind.setCurrentIndex(max(0,dialog.kind.findData(self.section if self.section in KINDS else 'movie')))
            dialog.sync_kind()
            dialog.show()
        if dialog.browser is not None and dialog.browser.isVisible():dialog.browser.raise_();dialog.browser.activateWindow();return
        dialog.raise_();dialog.activateWindow();dialog.setFocus()
        if already:self.status.setText('导入窗口已打开，请在其中确认设置')

    def start_import(self,path,kind,plugin=None,destination=None,batch=None):
        origin=(self.section,self.subtab)
        def complete(result):
            self.status.setText(f"导入 {result['imported']} · NFO 更新 {result.get('nfo_updated',0)} · 重复 {result['duplicates']} · 失败 {len(result['errors'])} · 警告 {len(result['warnings'])}")
            if self.detail_page is None and (self.section,self.subtab)==origin and self.section!=kind:self.navigate(kind)
            if kind in {'movie','series','vr'}:
                self.auto_scrape_import(path, kind, plugin, destination, work_ids=result.get('work_ids',[]))
        self.run_job('快速导入 · 时长与缺失图片稍后补充', lambda lib, p: lib.import_folder(path, kind, p, fast=True, cancelled=p.cancelled,include_work_ids=True), complete)
        for folder in (batch or []):
            self.start_import(folder, kind, plugin, destination)

    def auto_scrape_import(self, path, kind, plugin_id=None, destination=None, work_ids=None):
        if kind not in {'movie','series','vr'}:return
        config = self.library.setting('partition:' + kind, {})
        # None falls back to the saved partition rule; '' explicitly disables it.
        plugin_id = config.get('plugin') if plugin_id is None else plugin_id
        destination = config.get('destination','') if destination is None else destination
        if not plugin_id and not destination:
            self.status.setText(self.status.text()+' · 未启用导入后刮削，请在添加媒体中选择来源或配置分类默认来源')
            return
        def scrape(lib, progress):
            from .ingestion import enqueue, process_pending
            works = lib.query({'kinds': [kind], **({'ids':work_ids} if work_ids is not None else {'folder':str(Path(path).resolve())})})
            for work in works:
                enqueue(lib, work, plugin_id, destination,force=True)
            return process_pending(lib, progress, getattr(progress, 'cancelled', None), limit=max(1,len(works)),work_ids=[work['id'] for work in works])
        self.run_job('自动识别、补图与整理', scrape)

    def dragEnterEvent(self, event):
        # Delayed shell rendering and slow paths make toLocalFile()+is_dir()
        # unreliable (and IO-churning) while hovering; validate on drop instead.
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()

    def import_hint(self, text):
        QMessageBox.information(self, '导入', text)

    def dropEvent(self, event):
        folders = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if not local:continue
            try:
                path=Path(local)
                from .core import VIDEO_EXTENSIONS
                if path.is_dir() or path.is_file() and not path.is_symlink() and path.suffix.lower() in VIDEO_EXTENSIONS:
                    if local not in folders:folders.append(local)
            except OSError:continue
        if not folders:
            self.import_hint('拖入的内容里没有识别到文件夹或支持的视频文件。')
            return
        event.acceptProposedAction()
        self.import_path(folders[0], pending=folders[1:])
        if len(folders) > 1:
            self.status.setText(f'本次拖入 {len(folders)} 个文件或文件夹；确认设置后按相同选项加入队列。')

    def build_tree(self,items=None):
        self.tree.clear()
        roots = {}
        for w in (items if items is not None else self.library.query({'kinds':['other']})):
            for file in w['files']:
                root = Path(file['root'])
                if str(root) not in roots:
                    item = QTreeWidgetItem([root.name])
                    item.setData(0, Qt.ItemDataRole.UserRole, str(root))
                    self.tree.addTopLevelItem(item)
                    roots[str(root)] = item
                parent = roots[str(root)]
                cursor = root
                for part in Path(file['path']).relative_to(root).parts[:-1]:
                    cursor /= part
                    if str(cursor) not in roots:
                        node = QTreeWidgetItem([part])
                        node.setData(0, Qt.ItemDataRole.UserRole, str(cursor))
                        parent.addChild(node)
                        roots[str(cursor)] = node
                    parent = roots[str(cursor)]
        self.tree.expandToDepth(1)

    def folder_selected(self, item, column):
        self.filters['folder'] = item.data(0, Qt.ItemDataRole.UserRole)
        self.refresh()

    def stop_jobs(self):
        if self.lan_server:self.lan_server.downloads.cancel_all()
        for job in self.jobs:
            job.requestInterruption()
        self.cancel_job.setEnabled(False)
        self.status.setText('正在安全停止任务…')
        for title,function,callback,identifier,quiet in self.job_queue:
            self.task_journal.record(identifier,'background','cancelled',{'title':title},error='队列已停止')
            self._job_resources.pop(identifier,None)
        self.job_queue.clear()

    def run_job(self, title, function, callback=None, _identifier=None, quiet=False, resource='disk', background=False):
        if self._closing:
            return
        identifier=_identifier or uuid.uuid4().hex
        self._job_resources[identifier]=(resource,background)
        self._job_functions[identifier]=(title,function,callback,quiet)
        if len(self._job_functions)>32:self._job_functions.pop(next(iter(self._job_functions)))
        if self.jobs_paused or background and self.task_budget.playback or self.job_capacity_used()>=self.library.setting('background_concurrency',1):
            if len(self.job_queue)>=100:
                self._job_resources.pop(identifier,None);self._job_functions.pop(identifier,None)
                self.status.setText('后台队列已满，请等待部分任务完成');return
            self.job_queue.append((title,function,callback,identifier,quiet))
            if not quiet:self.task_journal.record(identifier,'background','queued',{'title':title})
            self.status.setText(f'已排队：{title} · 等待 {len(self.job_queue)} 项')
            return
        if not quiet:self.task_journal.record(identifier,'background','running',{'title':title})
        if not quiet:self.status.setText(title + '…')
        self.job_progress.setRange(0, 0)
        if not quiet:self.job_area.show();self.job_progress.show();self.job_counter.show();self.job_counter.setText('准备中')
        self.cancel_job.setEnabled(True)
        self.cancel_job.setVisible(not quiet)
        job = Job(self.library.directory, function, self)
        job.task_identifier=identifier
        job.budget=self.task_budget
        job.resource=resource;job.background=background
        self.jobs.append(job)
        last_refresh = [time.monotonic()]
        started=time.monotonic();last_saved=[0];last_counter=[started,0]
        def show_progress(done, total, message):
            if job not in self.jobs:return
            self.job_area.show();self.job_progress.show();self.job_counter.show();self.cancel_job.show()
            if total>2147483647:
                self.job_progress.setRange(0,10000)
                self.job_progress.setValue(min(10000,int(done*10000//total)))
                self.job_progress.setFormat('%p%')
            else:
                self.job_progress.setRange(0,total)
                self.job_progress.setValue(done if total else 0)
                self.job_progress.setFormat('%v / %m · %p%')
            self.job_counter.setText(f'{done} / {total}' if total else '扫描中')
            self.status.setText(title + ' · ' + message)
            if not quiet and time.monotonic()-last_saved[0]>=1:
                current=time.monotonic();elapsed=max(.001,current-last_counter[0]);speed=max(0,done-last_counter[1])/elapsed;last_counter[:]=[current,done]
                self.task_journal.record(identifier,'background','paused' if job.paused.is_set() else 'running',
                                  {'title':title,'progress':{'completed':done,'total':total,'stage':message,'units_per_second':round(speed,2),'unit':'bytes' if '下载' in title and '检查' not in title and total>1048576 else 'items'}})
                last_saved[0]=time.monotonic()
            if title.startswith('快速导入') and self.detail_page is None and time.monotonic() - last_refresh[0] > 2:
                self.refresh()
                last_refresh[0] = time.monotonic()
        job.progress.connect(show_progress)
        # Deliver completion after the thread exits, allowing dependent jobs to start.
        outcome = {}
        job.done.connect(lambda value: outcome.update(value=value))
        job.failed.connect(lambda error: outcome.update(error=error))
        def finished():
            self.jobs.remove(job)
            self._job_resources.pop(identifier,None)
            # Keep the fixed task strip in place while completion callbacks and
            # the next queued job run; hiding it between jobs resizes the page.
            job.deleteLater()
            if self._closing:
                if not self.jobs and self._browse_job is None:
                    QTimer.singleShot(0, self.close)
                return
            if not quiet:
                cancelled=isinstance(outcome.get('value'),dict) and outcome['value'].get('cancelled')
                self.task_journal.record(identifier,'background','failed' if 'error' in outcome else 'cancelled' if cancelled else 'done',{'title':title},outcome.get('value') if isinstance(outcome.get('value'),dict) else {},outcome.get('error'))
            from .images import image_cache
            image_cache().invalidate()
            if not quiet or outcome.get('value',{}).get('imported') or outcome.get('value',{}).get('updated'):self.refresh()
            if title=='书签截图' and self.detail_page:self.detail_page.refresh_bookmarks()
            if 'error' in outcome:
                self.status.setText(title + '失败：' + outcome['error'])
                QMessageBox.warning(self, title, outcome['error'])
            elif isinstance(outcome.get('value'), dict) and outcome['value'].get('cancelled'):
                self.status.setText('任务已停止，已完成内容保留')
            else:
                self._job_functions.pop(identifier,None)
                if not quiet or outcome.get('value',{}).get('imported') or outcome.get('value',{}).get('updated'):self.status.setText(title + '完成')
                elif outcome.get('value',{}).get('offline'):self.status.setText('监控目录离线，已保留原有媒体资料')
                if callback:
                    callback(outcome.get('value'))
            self.start_queued_jobs()
            busy=bool(self.jobs or self.job_queue)
            for control in (self.job_progress,self.job_counter,self.cancel_job):control.setVisible(busy)
            self.job_area.setVisible(busy)
        job.finished.connect(finished)
        job.start()

    def step_playback(self, direction):
        if self.random_active:
            self.queue_play(direction)
        elif self.player.file:
            items = [w for w in self.current_items if w.get('files')]
            index = next((i for i, w in enumerate(items) if w['id'] == self.player.file['work_id']), -1)
            if index >= 0 and 0 <= index + direction < len(items):
                self.play_work(items[index + direction]['id'])

    def play_work(self, work_id, random=False):
        try:
            self.random_active = random
            self.player.open_file(self.library.resume_file(work_id))
        except Exception as exc:
            QMessageBox.warning(self, '无法播放', str(exc))

    def play_file(self, file):
        self.random_active = False
        self.player.open_file(file)

    def shuffle(self, filters=None):
        if not isinstance(filters, dict):
            if self._browse_job is not None or self._browse_pending is not None:
                self.status.setText('正在读取当前列表，完成后可随机播放。');return
            filters = self.effective_filters()
            # current_items contains the complete query result, beyond the first
            # rendered page, and includes recommendation / next-episode scope.
            filters['ids']=[item['id'] for item in self.current_items if item.get('id') is not None and item.get('files')]
            filters.pop('continue',None)  # The rendered resume set includes unstarted next episodes.
        queue = self.library.shuffle(filters)
        if queue['ids']:
            self.play_work(queue['ids'][0], random=True)
            self.status.setText(f"已对全部 {len(queue['ids'])} 部作品洗牌，本轮不重复")
        else:
            QMessageBox.information(self, '随机队列', '当前范围没有本地视频。')

    def queue_play(self, delta):
        work_id = self.library.queue_step(delta)
        if work_id:
            self.play_work(work_id, random=True)
        else:
            self.random_active = False
            self.player.finish()
            self.status.setText('本轮随机队列已结束，可主动重新洗牌。')

    def show_queue(self):
        from .catalog_ui import queue_editor
        queue_editor(self)

    def discover(self):
        plugins = [p for p in Plugins(self.library).installed() if p['config'].get('enabled') and 'discover' in p['capabilities']]
        if not plugins:
            QMessageBox.information(self, '影片发现', '请先安装并启用支持 discover 的插件。')
            return
        selected = self.source_filter.currentData() if self.section == 'discover' else ''
        self.run_job('刷新影片发现', lambda lib, p: self.refresh_plugins(lib, [x['id'] for x in plugins if not selected or x['id'] == selected]))

    @staticmethod
    def refresh_plugins(library, ids):
        errors = []
        for plugin_id in ids:
            try:
                Plugins(library).refresh(plugin_id)
            except ImportCancelled:raise
            except Exception as exc:
                errors.append(f'{plugin_id}: {exc}')
        if errors:
            raise RuntimeError('\n'.join(errors))

    def schedule_discovery(self):
        if self._closing or self.job_queue or self.jobs_paused:
            return
        if any(j.isRunning() for j in self.jobs):
            return
        due = [p['id'] for p in Plugins(self.library).installed() if p['config'].get('enabled') and 'discover' in p['capabilities'] and p['config'].get('auto_refresh', False)
               and time.time() - max(p['config'].get('last_refresh', 0), p['config'].get('last_attempt', 0)) > max(1, p['config'].get('interval_hours', 24)) * 3600]
        if due:
            self.run_job('定期发现新片', lambda lib, p: self.refresh_plugins(lib, due), resource='network', background=True)

    def show_tasks(self):
        if getattr(self,'tasks_dialog',None) is not None:
            self.tasks_dialog.show();self.tasks_dialog.raise_();return
        from .background import run_background
        from . import tasks
        dialog = QDialog(self);self.tasks_dialog=dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(lambda:setattr(self,'tasks_dialog',None) if self.tasks_dialog is dialog else None)
        dialog.finished.connect(lambda _code:setattr(self,'tasks_dialog',None) if self.tasks_dialog is dialog else None)
        dialog.resize(950, 650)
        dialog.setWindowTitle('任务中心')
        layout = QVBoxLayout(dialog)
        log_row=QHBoxLayout();log_path=ElidedLabel('日志目录：'+str(self.library.directory))
        log_path.setToolTip(str(self.library.directory));log_row.addWidget(log_path,1)
        log_row.addWidget(button('复制日志路径',lambda:QApplication.clipboard().setText(str(self.library.directory))))
        log_row.addWidget(button('打开日志目录',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.directory)))))
        layout.addLayout(log_row)
        task_scope=QComboBox();task_scope.setObjectName('taskScope')
        for title,key in [('全部任务','all'),('进行中 / 已暂停','active'),('待确认 / 等待重试','pending'),('失败 / 部分完成','failed'),('已完成 / 已停止','history')]:task_scope.addItem(title,key)
        layout.addWidget(task_scope)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(['类型','状态','更新时间','详情 / 失败原因'])
        table.setWordWrap(False);table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.verticalHeader().setDefaultSectionSize(32)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column,width in enumerate((180,100,180)):table.setColumnWidth(column,width)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        rows=[];page=[0]
        page_status=label('每页显示 100 条任务')
        loading=[False];closed=[False]
        dialog.finished.connect(lambda _code:closed.__setitem__(0,True))
        def reload():
            if loading[0] or closed[0] or self._closing:return
            loading[0]=True
            def ready(records):
                loading[0]=False
                if not closed[0]:apply_records(records)
            def failed(error):
                loading[0]=False
                if not closed[0]:table.setToolTip('任务暂未读出，可稍后自动重试：'+error)
            offset=page[0]*100;only_pending=task_scope.currentData()
            run_background(self,lambda job:tasks.snapshot(self.library.directory,offset,only_pending),ready,failed)
        def apply_records(records):
            if page[0]>0 and not records:page[0]-=1;reload();return
            previous_page.setEnabled(page[0]>0);next_page.setEnabled(len(records)==100);page_status.setText(f'第 {page[0]+1} 页 · 每页 100 条')
            selected=rows[table.currentRow()]['id'] if 0<=table.currentRow()<len(rows) else None
            bar=table.verticalScrollBar();position=bar.value();table.setUpdatesEnabled(False)
            rows[:]=records
            table.setRowCount(len(rows))
            for index,task in enumerate(rows):
                payload=json.loads(task['payload']);progress=payload.get('progress',{})
                if not progress and 'bytes' in payload:progress={'completed':payload['bytes'],'total':payload.get('total',0),'stage':payload.get('message','下载'),'path':payload.get('target',payload.get('path','')),'unit':'bytes','units_per_second':payload.get('bytes_per_second',0)}
                quantity=(f"{progress.get('completed',0)/1048576:.1f} / {progress.get('total',0)/1048576:.1f} MiB" if progress.get('unit')=='bytes' else f"{progress.get('completed',0)} / {progress.get('total',0)}")
                detail=task['error'] or (f"{quantity} · {progress.get('stage','')} · {progress.get('path','')}" if progress else task['result'])
                if progress.get('units_per_second') is not None:detail+=(f" · {progress['units_per_second']/1048576:.2f} MiB/s" if progress.get('unit')=='bytes' else f" · {progress['units_per_second']} 项/秒")
                state=task['status']
                if self.lan_server and self.lan_server.downloads.paused.is_set() and task['kind']=='download-library' and state in {'running','queued','importing'}:state='paused'
                states={'pending':'待确认','retry':'等待自动重试','queued':'排队中','running':'进行中','paused':'已暂停','importing':'入库中','failed':'失败','partial':'部分完成','done':'已完成','cancelled':'已停止','external':'外部工具处理'}
                kinds={'ingest':'自动入库','import':'导入','media':'补充媒体','scrape':'刮削','download':'HTTP 下载','download-library':'下载并入库','match':'匹配确认','move':'文件整理','background':'后台处理'}
                for column,text in enumerate([payload.get('title',kinds.get(task['kind'],task['kind'])),states.get(state,state),task['updated'][:19],detail]):
                    text=str(text).replace('\n',' ')[:2000]
                    item=table.item(index,column)
                    if item is None:item=QTableWidgetItem();table.setItem(index,column,item)
                    if item.text()!=text:item.setText(text);item.setToolTip(text)
                    if column==1:item.setForeground(QColor('#e98383' if state in {'failed','partial'} else '#6bc9a5' if state=='done' else '#00a4dc' if state in {'running','importing'} else '#e7c567' if state=='paused' else '#cccccc'))
                if task['id']==selected:table.selectRow(index)
            bar.setValue(position);table.setUpdatesEnabled(True)
        task_scope.currentIndexChanged.connect(lambda _: (page.__setitem__(0,0),reload()))
        reload();timer=QTimer(dialog);timer.setInterval(1000);timer.timeout.connect(reload);timer.start()
        layout.addWidget(table)
        def turn_page(direction):
            if loading[0]:return
            page[0]=max(0,page[0]+direction);table.clearSelection();table.setCurrentCell(-1,-1);reload()
        pagination=QHBoxLayout();previous_page=button('上一页',lambda:turn_page(-1));next_page=button('下一页',lambda:turn_page(1))
        pagination.addWidget(previous_page);pagination.addWidget(page_status,1);pagination.addWidget(next_page);layout.addLayout(pagination)
        paused=QCheckBox('暂停后台队列（在安全点暂停处理，播放与浏览继续）');paused.setChecked(self.jobs_paused);paused.toggled.connect(self.pause_jobs);layout.addWidget(paused)
        def cancel_selected():
            index=table.currentRow()
            if not 0<=index<len(rows):return
            identifier=json.loads(rows[index]['payload']).get('parent_task_id',rows[index]['id'])
            if self.lan_server and self.lan_server.downloads.cancel(identifier):return
            for job in self.jobs:
                if getattr(job,'task_identifier',None)==identifier:job.requestInterruption();return
            for queued in list(self.job_queue):
                if queued[3]==identifier:self.job_queue.remove(queued);self._job_resources.pop(identifier,None);self.task_journal.record(identifier,'background','cancelled',{'title':queued[0]});reload();return
        layout.addWidget(button('停止选中后台任务',cancel_selected))
        def inspect_task():
            from .dialogs import save_file_name
            index=table.currentRow()
            if not 0<=index<len(rows):return
            identifier=rows[index]['id']
            detail=QDialog(dialog);detail.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);detail.resize(850,600);detail.setWindowTitle('任务详情')
            content=QVBoxLayout(detail);text=QPlainTextEdit('正在后台读取任务详情…');text.setReadOnly(True);text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap);content.addWidget(text)
            alive=[True];detail.finished.connect(lambda _code:alive.__setitem__(0,False))
            def ready(data):
                if alive[0]:text.setPlainText(('记录较大，此处显示预览；可导出完整 JSON。\n\n' if data['truncated'] else '')+data['text'])
            run_background(self,lambda job:tasks.record(self.library.directory,identifier,preview=True),ready,lambda error:text.setPlainText(error) if alive[0] else None)
            def export():
                destination=save_file_name(detail,'导出完整任务记录',identifier+'.json','JSON (*.json)')
                if destination:run_background(self,lambda job:tasks.export(self.library.directory,identifier,destination,job.isInterruptionRequested),lambda path:text.appendPlainText('\n已导出：'+path) if alive[0] else None)
            content.addWidget(button('导出完整 JSON',export));content.addWidget(button('关闭',detail.accept));detail.show()
        layout.addWidget(button('查看完整进度 / 结果 / 错误', inspect_task))
        def retry():
            index=table.currentRow()
            if not 0<=index<len(rows):return
            identifier=rows[index]['id']
            def read(job):
                task=tasks.record(self.library.directory,identifier,retry=True)
                if task['kind']=='download' and task['payload'].get('parent_task_id'):task=tasks.record(self.library.directory,task['payload']['parent_task_id'],retry=True)
                return task
            run_background(self,read,lambda task:retry_task(task) if not closed[0] else None)
        def retry_task(task):
            payload=task['payload']
            if task['status'] in {'running','queued','paused'}:return
            if task['kind']=='background' and task['id'] in self._job_functions:
                title,function,callback,quiet=self._job_functions[task['id']];dialog.accept();self.run_job(title,function,callback,quiet=quiet)
            elif task['kind'] == 'move':
                dialog.accept()
                self.run_job('恢复文件整理', lambda lib, p: execute_move(lib, task_id=task['id'],cancelled=p.cancelled))
            elif task['kind'] == 'import':
                dialog.accept()
                candidates=task.get('candidates') or payload.get('candidates') or None
                self.run_job('重试导入失败项' if candidates else '继续导入', lambda lib, p: lib.import_folder(payload['root'], payload['kind'], p, fast=payload.get('fast',True), cancelled=p.cancelled,candidates=candidates))
            elif task['kind']=='download':
                from .downloads import download_direct
                dialog.accept();self.run_job('重试直接下载',lambda lib,p:download_direct(lib,payload['plugin'],payload['url'],payload['target'],p,p.cancelled))
            elif task['kind']=='download-library' and type(payload.get('index')) is int:
                from .downloads import download_to_library
                dialog.accept();self.run_job('重试下载入库',lambda lib,p:download_to_library(lib,payload['work_id'],payload['index'],p,p.cancelled,directory=payload.get('directory')))
            elif task['kind'] == 'media':
                dialog.accept()
                with self.library.db:
                    self.library.db.execute('UPDATE import_cache SET pending=1 WHERE file_id=?',(payload['file_id'],))
                self.schedule_media()
            elif task['kind'] == 'ingest':
                dialog.accept()
                if task['status'] == 'pending' and payload.get('candidates'):
                    from .matching import CandidatePicker, apply_match
                    plugin=next((item for item in Plugins(self.library).installed() if item['id']==payload['plugin']),None)
                    if not plugin or not plugin['config'].get('enabled'):
                        QMessageBox.information(self,'刮削来源','请先启用此任务的影片刮削插件。');return
                    picker=CandidatePicker(self.library.directory,plugin['id'],payload['candidates'],self)
                    picker.setWindowTitle('确认匹配 · '+payload.get('title',''))
                    accepted=picker.exec();candidate=picker.selection();picker.deleteLater()
                    if accepted and candidate is not None:
                        self.run_job('确认资料并继续自动入库',lambda lib,p:apply_match(lib,plugin,'search',candidate,payload['work_id']))
                elif task['status'] == 'pending' and payload.get('stage') == 'identify':
                    self.open_details(payload['work_id'])
                else:
                    payload.update(attempts=0, next_attempt=0)
                    self.library.task(task['id'], 'ingest', 'queued', payload)
                    self.schedule_watched()
            elif task['kind'] == 'match':
                dialog.accept()
                self.open_details(payload['work_id'])
            elif task['kind'] == 'scrape':
                QMessageBox.information(dialog, '重试刮削', '请在影片详情中重新刮削，或在发现页刷新；搜索结果仍需确认匹配。')
        layout.addWidget(button('恢复 / 重试选中任务', retry, True))
        dialog.show()

    def render_stats(self,stats=None,report=None,history=None):
        clear(self.stats_layout)
        if stats is None:stats=self.library.stats()
        self.subtitle.setText('真实播放会话 · 严格超过 600 秒计一次有效播放 · 暂停和跳转不累计')
        if self.subtab == 0:
            grid = QGridLayout()
            for i, (title, value) in enumerate([('实际观看时长',f"{stats['seconds']/3600:.1f} 小时"),('有效播放',str(stats['valid'])),('播放会话',str(stats['sessions'])),('看过的电影',str(stats['movies'])),('看过的电视剧',str(stats['series']))]):
                panel = QFrame()
                column = QVBoxLayout(panel)
                column.addWidget(label(title, 'subtitle'))
                column.addWidget(label(value, 'metric'))
                grid.addWidget(panel, i//3, i%3)
            self.stats_layout.addLayout(grid)
            self.bar_section('重复观看最多', stats['repeat'])
            self.bar_section('最常观看演员', stats['actors'], True)
            self.bar_section('最常观看导演', stats['directors'], True)
        elif self.subtab in {1,2,3}:
            key = {1:'days',2:'weeks',3:'months'}[self.subtab]
            self.bar_section(self.tabs.tabText(self.subtab), stats[key], True, chronological=True)
        elif self.subtab == 4:
            from datetime import datetime
            year_box = QComboBox()
            years = sorted(set(stats['years']) | {str(datetime.now().year)}, reverse=True)
            year_box.addItems(years)
            selected = str(getattr(self, 'report_year', datetime.now().year))
            year_box.setCurrentText(selected if selected in years else years[0])
            def change_year(value):
                self.report_year = int(value)
                self.refresh()
            year_box.currentTextChanged.connect(change_year)
            self.stats_layout.addWidget(year_box)
            report = report or self.library.annual_report(int(year_box.currentText()))
            self.stats_layout.addWidget(label(f"{report['year']} 年 · {report['seconds']/3600:.1f} 小时 · {report['valid']} 次有效播放 · {report['distinct']} 部不同作品", 'heading'))
            self.stats_layout.addWidget(label(f"电影 {report['movies']} 部 / 电视剧 {report['series']} 部 / 播放会话 {report['sessions']} 次", 'subtitle'))
            self.bar_section('年度观看最多', report['titles'], True)
            self.bar_section('年度标签偏好', report['tags'], True)
        elif self.subtab == 5:
            self.bar_section('媒体类型', {KINDS[k]:v for k,v in stats['types'].items()}, True)
            self.bar_section('标签偏好', stats['tags'], True)
        elif self.subtab == 6:
            self.bar_section('个人评分分布 · 未评分不计入', {str(i):stats['ratings'].get(str(i),0) for i in range(1,11)}, chronological=True)
        elif self.subtab == 7:
            for row in (history if history is not None else self.library.db.execute('SELECT s.started,s.watched,w.title FROM sessions s JOIN files f ON s.file_id=f.id JOIN works w ON w.id=f.work_id ORDER BY s.started DESC LIMIT 200')):
                self.stats_layout.addWidget(label(f"{row['started'][:19]}  ·  {row['title']}  ·  实际 {row['watched']/60:.1f} 分钟"))
        self.stats_layout.addStretch()

    def bar_section(self, title, values, hours=False, chronological=False):
        self.stats_layout.addWidget(label(title, 'heading'))
        items = sorted(values.items(), key=lambda pair: pair[0])[-30:] if chronological else sorted(values.items(), key=lambda pair:-pair[1])[:12]
        maximum = max(values.values(), default=1) or 1
        if not items:
            self.stats_layout.addWidget(label('还没有观看记录。播放你的第一部影片后，这里会呈现真实数据。', 'subtitle'))
        for key, value in items:
            row = QHBoxLayout()
            text = label(str(key))
            text.setMinimumWidth(140)
            row.addWidget(text)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(round(value / maximum * 1000))
            bar.setTextVisible(False)
            row.addWidget(bar, 1)
            row.addWidget(label(f'{value/3600:.2f} 小时' if hours else str(value)))
            self.stats_layout.addLayout(row)

    def apply_lan(self, enabled, port):
        from .server import LanServer
        previous = self.lan_server
        if previous:
            previous.stop()
        self.lan_server = None
        try:
            if enabled:
                server = LanServer(self.library.directory,port=port,remote=self.remote,budget=self.task_budget)
                server.start()
                server.downloads.pause(self.jobs_paused)
                self.lan_server = server
            self.library.set_setting('lan', {'enabled':enabled,'port':port})
        except Exception:
            if previous:
                previous.start()
                self.lan_server = previous
            raise

    def updater(self):
        if not hasattr(self,'desktop_updates'):
            from .updates_ui import DesktopUpdates
            self.desktop_updates=DesktopUpdates(self)
        return self.desktop_updates

    def check_updates(self):
        self.updater().show();self.desktop_updates.check()

    def settings(self):
        from .settings import Settings
        Settings(self).exec()
        if self._closing:return
        if self.section=='discover':self.discovery_panel.reload_sources()
        self.refresh()
        if self.detail_page is not None:self.reload_details(self.detail_page.work_id)

    def closeEvent(self, event):
        if getattr(self,'_shutdown_complete',False):event.accept();return
        if not self._closing:self.player.close()
        self._closing = True
        self.task_budget.set_playback(False);self.task_budget.set_paused(False)
        self.discovery_images.stop()
        if getattr(self,'import_form',None):self.import_form.reject()
        self.resource_scheduler.stop();self.watch_scheduler.stop();self.remote.timer.stop();self.remote.clear()
        for title,function,callback,identifier,quiet in self.job_queue:
            if not quiet:self.task_journal.record(identifier,'background','cancelled',{'title':title},error='应用关闭，未执行队列任务')
        self.job_queue.clear()
        if self.jobs or self._browse_job is not None or self._auxiliary_jobs or not self.discovery_images.idle:
            for worker in self._auxiliary_jobs:worker.requestInterruption()
            self._closing = True
            self._browse_pending=None
            if self._browse_job is not None:self._browse_job.requestInterruption()
            self.scheduler.stop()
            self.media_scheduler.stop()
            self.status.setText('正在停止任务并保存已完成记录…')
            for job in self.jobs:
                job.paused.clear();job.requestInterruption()
            self.hide()
            event.ignore()
            QTimer.singleShot(100,self.close)
            return
        self.player.close()
        if not self.player.playback_journal.stop():
            self.status.setText('正在后台保存最后的播放记录…')
            event.ignore()
            QTimer.singleShot(100,self.close)
            return
        if self.player.playback_journal.unsaved_error:
            if getattr(self,'_journal_save_prompt_active',False):event.ignore();return
            self._journal_save_prompt_active=True
            prompt=QMessageBox(QMessageBox.Icon.Warning,'播放记录尚未保存',self.player.playback_journal.unsaved_error,parent=self)
            retry=prompt.addButton('重试保存',QMessageBox.ButtonRole.AcceptRole)
            cancel=prompt.addButton('取消退出',QMessageBox.ButtonRole.RejectRole)
            discard=prompt.addButton('仍然退出',QMessageBox.ButtonRole.DestructiveRole)
            prompt.setDefaultButton(cancel)
            prompt.setInformativeText('仍然退出可能丢失最近未保存的观看进度；不会改动视频文件。')
            try:prompt.exec()
            finally:self._journal_save_prompt_active=False
            if prompt.clickedButton() is not discard:
                keep_open=prompt.clickedButton() is not retry
                self.player.playback_journal.retry(keep_open=keep_open)
                event.ignore()
                if keep_open:
                    self._closing=False
                    self.showNormal()
                    self.discovery_images.resume()
                    for timer in (self.scheduler,self.media_scheduler,self.watch_scheduler,self.resource_scheduler,self.remote.timer):timer.start()
                    self.status.setText('已取消退出，播放记录将在后台重试保存')
                else:QTimer.singleShot(100,self.close)
                return
        self.scheduler.stop()
        self.media_scheduler.stop()
        if self.lan_server:
            self.lan_server.stop()
        self.task_journal.stop()
        self.library.close()
        self._shutdown_complete=True
        event.accept()
        self.shutdownFinished.emit()
        if getattr(self,'_update_pending',False):QApplication.instance().quit()
