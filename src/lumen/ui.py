from __future__ import annotations
import json
from html import escape
from pathlib import Path
import time
import threading
import uuid
from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer, QUrl, QRect, QPoint
from PySide6.QtGui import QPixmap, QIcon, QColor, QPainter, QFont, QDesktopServices, QPixmapCache, QLinearGradient, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
 QGridLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
 QFileDialog, QMessageBox, QInputDialog, QListWidget, QListWidgetItem, QAbstractItemView, QTreeWidget,
 QTreeWidgetItem, QSplitter, QTabBar, QScrollArea, QPlainTextEdit, QTableWidget, QTableWidgetItem,
 QHeaderView, QStackedWidget, QProgressBar, QStyledItemDelegate, QStyle, QMenu, QCompleter, QSizePolicy)
from .core import Library, thumbnail, tool, ImportCancelled
from .plugins import Plugins
from .files import plan_move, execute_move
from .player import Player
from .presentation import rating_text
from .theme import STYLE
from .components import ActionButton,FlowLayout,chip,icon,ElidedLabel

KINDS = {'movie': '电影', 'series': '电视剧', 'vr': 'VR电影', 'fans': 'Fans', 'other': '其他'}


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

    def cancelled(self):
        while self.paused.is_set() and not self.isInterruptionRequested():time.sleep(.1)
        return self.isInterruptionRequested()

    def run(self):
        library = None
        acquired=False
        try:
            if self.budget:
                self.progress.emit(0,0,'等待后台处理名额')
                self.budget.acquire(self.cancelled);acquired=True
            library=Library(self.directory)
            library.parent_task_id=getattr(self,'task_identifier',None)
            last_report=[0,None];latest=[None]
            def report(done, total, message):
                if self.cancelled():raise ImportCancelled('任务已停止')
                latest[0]=(done,total,message)
                if time.monotonic()-last_report[0]>=.1 or total>0 and done>=total:
                    self.progress.emit(done,total,message);last_report[:]=[time.monotonic(),latest[0]]
            report.cancelled = self.cancelled
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
    def __init__(self, play, parent=None):
        super().__init__(parent)
        self.play = play

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
        unfinished = next((f for f in files if f.get('position',0)>0 and not f.get('completed')),None)
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
        return QSize(280, 238) if data.get('_landscape') else QSize(190, 351)


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
        self.query.clear();self.actor.setEditText('');self.folder.clear();self.favorite.setChecked(False);self.watched.setCurrentIndex(0)
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
        path=QFileDialog.getExistingDirectory(self,'选择目录范围',self.folder.text())
        if path:self.folder.setText(path)

    def filters(self):
        return {'query':self.query.text().strip(),'kinds':[key for key,control in self.types.items() if control.isChecked()],
                **{key:list(dict.fromkeys(part.strip() for part in field.text().replace('，',',').split(',') if part.strip())) for key,field in self.fields.items()},
                **{key:field.value() for key,field in self.numbers.items() if field.value()},
                'watch_state':self.watched.currentData(),'folder':self.folder.text().strip(),'actor':self.actor.text(),
                **({'watchlist':True} if self.original.get('watchlist') else {}),
                **({'favorite':True} if self.favorite.isChecked() else {})}


class MetadataLinks(QWidget):
    linkActivated=Signal(str)


class CoverImage(QLabel):
    activated=Signal()

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('点击放大封面 · 滚轮缩放 / 拖动查看')
        self.setAccessibleName('放大封面')

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit();event.accept();return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
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
        outer.setContentsMargins(34, 30, 34, 24)
        outer.setSpacing(16)
        outer.addWidget(ActionButton('返回上一页','back',self.accept),alignment=Qt.AlignmentFlag.AlignLeft)
        self.setMinimumHeight(760)
        top = QHBoxLayout();top.setSpacing(28)
        poster = self.poster = CoverImage()
        poster.setFixedSize(210, 315)
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setScaledContents(False)
        poster.setStyleSheet('background: #181818; border: none;')
        self.poster_path=w['thumbnail']
        poster.activated.connect(self.view_cover)
        top.addWidget(poster,0,Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout();info.setSpacing(12)
        heading=label(w['title'],'detailTitle');heading.setWordWrap(True);info.addWidget(heading)
        facts=QHBoxLayout();facts.setSpacing(16)
        if w['kind']!='fans':facts.addWidget(label(str(w['year'] or '年份待补充'),'subtitle'))
        facts.addWidget(label('Fans · 作者文件夹' if w['kind']=='fans' else KINDS[w['kind']],'subtitle'))
        duration=sum(file['duration'] for file in w['files']) if w['kind']=='fans' else max((file['duration'] for file in w['files']),default=0)
        if w['kind']=='fans':facts.addWidget(label(f"{len(w['files'])} 个视频",'subtitle'))
        if duration:facts.addWidget(label(f'{duration/60:.0f} 分钟','subtitle'))
        source=next((source for source in w['sources'] if source.get('rating') is not None),None)
        if source:facts.addWidget(label(f"★ {source['rating']:.1f}",'sourceScore'))
        facts.addStretch();info.addLayout(facts)
        actions=QHBoxLayout();actions.setSpacing(8)
        play=button('播放' if not any(file['position'] for file in w['files']) else '继续播放',lambda:window.play_work(work_id),True)
        play.setIcon(icon('play','#ffffff',True));play.setMinimumHeight(46);play.setMinimumWidth(170);play.setEnabled(bool(w['files']));actions.addWidget(play)
        self.favorite_action=ActionButton('已收藏' if w['favorite'] else '收藏','heart',checked=bool(w['favorite']),accent='#f4779b');self.favorite_action.setObjectName('favoriteAction')
        self.favorite_action.clicked.connect(lambda value:self.personal(favorite=value));actions.addWidget(self.favorite_action)
        self.watchlist_action=ActionButton('已想看' if w['watchlist'] else '想看','bookmark',checked=bool(w['watchlist']))
        self.watchlist_action.clicked.connect(lambda value:self.personal(watchlist=value));actions.addWidget(self.watchlist_action)
        self.rating_action=ActionButton(f"{w['rating']} 分" if w['rating'] else '评分','star',self.choose_rating,accent='#e7c567');self.rating_action.setVisible(w['kind']!='other');self.rating_action.setToolTip('我的评分');self.rating_action.setAccessibleName('我的评分');actions.addWidget(self.rating_action)
        more=ActionButton('更多操作','more').icon_only();self.management_menu=QMenu(more)
        if w['kind'] in {'movie','series','vr'}:
            self.management_menu.addAction(icon('search'),'刮削匹配…',self.scrape)
            self.management_menu.addAction('编辑资料 / 锁定…',self.edit)
            self.management_menu.addSeparator()
        self.management_menu.addAction(icon('folder'),'整理文件…',self.organize)
        if w['kind']!='fans':
            self.management_menu.addAction('从 NFO 补充图片…',lambda:window.import_nfo_artwork(work_id))
            self.management_menu.addAction('刮削演员头像…',self.scrape_actor_photo)
        self.management_menu.addAction('重新截取封面…',self.recapture)
        self.management_menu.addAction('整部标记已看',lambda:window.catalog_watch(work_id,'completed'))
        self.management_menu.addAction('整部重置进度',lambda:window.catalog_watch(work_id,'unwatched'))
        self.management_menu.addAction('从头播放',lambda:window.catalog_restart(work_id))
        self.management_menu.addAction('加入播放队列',lambda:window.library.edit_queue([*window.library.setting('queue',{'ids':[]})['ids'],work_id]))
        self.management_menu.addAction('仅移出媒体库…',lambda:window.remove_catalog_work(work_id))
        if w['kind'] in {'movie','series','vr'}:self.management_menu.addAction('合并重复作品…',self.merge_duplicate)
        if w['kind']=='fans':self.management_menu.addAction('合并同作者文件夹…',self.merge_fans_folders)
        self.dislike_action=self.management_menu.addAction(icon('ban'),'不感兴趣');self.dislike_action.setCheckable(True);self.dislike_action.setChecked(bool(w['disliked']));self.dislike_action.triggered.connect(lambda value:self.personal(disliked=value))
        more.setMenu(self.management_menu);actions.addWidget(more);actions.addStretch();info.addLayout(actions)
        def links(values,field):
            # Keep the navigation signal available for keyboard and assistive actions.
            widget=MetadataLinks();flow=FlowLayout(widget)
            if field=='actor' and values:
                caption=label('主演','eyebrow');caption.setMinimumHeight(30);flow.addWidget(caption)
            for index,value in enumerate(values):flow.addWidget(chip(value,lambda checked=False,index=index:widget.linkActivated.emit(str(index))))
            widget.linkActivated.connect(lambda index:window.search_metadata(field,values[int(index)]))
            info.addWidget(widget);widget.setVisible(bool(values));return widget
        self.tag_links=links(w['metadata'].get('tags',[]),'tags_all')
        self.actor_links=links([actor['name'] for actor in w['metadata'].get('actors',[])],'actor')
        if w['metadata'].get('released'):info.addWidget(label('上映 / 首播  '+str(w['metadata']['released']),'subtitle'))
        description=label(('按作者归组，包含此作者文件夹及下级目录的视频。多个目录属于同一作者时，可在“更多操作”中合并，原始文件保留。' if w['kind']=='fans' else w['metadata'].get('overview','暂无简介，可通过刮削补充。')) if w['kind']!='other' else '保留原始目录结构。')
        description.setWordWrap(True);info.addWidget(description,1)
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
        watch_row=QHBoxLayout()
        def mark_episode(state):
            item=self.files.currentItem()
            if item:self.library.set_watched(self.work_id,state,item.data(Qt.ItemDataRole.UserRole)['id']);self.window.open_details(self.work_id,fetch=False)
        watch_row.addWidget(button('当前视频标为已看',lambda:mark_episode('completed')));watch_row.addWidget(button('重置当前视频进度',lambda:mark_episode('unwatched')));outer.addLayout(watch_row)
        outer.addWidget(self.files)
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
        outer.insertWidget(3,self.gallery_heading)
        self.still_gallery = StillGallery()
        self.still_gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.still_gallery.setFlow(QListWidget.Flow.LeftToRight)
        self.still_gallery.setWrapping(False)
        self.still_gallery.setIconSize(QSize(288,162))
        self.still_gallery.setGridSize(QSize(308,192))
        self.still_gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.still_gallery.setFixedHeight(218)
        self.still_gallery.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.still_gallery.horizontalScrollBar().valueChanged.connect(self.render_artwork)
        outer.insertWidget(4,self.still_gallery)
        self.still_gallery.itemClicked.connect(self.show_still)
        self.set_stills(still_paths(w))
        self.still_gallery.itemDoubleClicked.connect(self.fullscreen_stills)
        outer.addWidget(button('全屏浏览剧照',lambda:self.fullscreen_stills(self.still_gallery.currentItem() or self.still_gallery.item(0))))
        self.gallery_status=label('','subtitle')
        self.gallery_status.setWordWrap(True)
        outer.insertWidget(5,self.gallery_status)
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
        if getattr(self,'expanded_still_path',None):
            width=min(1400,max(320,self.width()-68));height=max(200,min(720,round(width*9/16)))
            if self.expanded_still.height()!=height:self.expanded_still.setFixedHeight(height)
            image=cache.request(self.expanded_still_path,QSize(width,height))
            preview_key=(image.cacheKey(),width,height)
            if not image.isNull() and getattr(self,'_preview_key',None)!=preview_key:
                self.expanded_still.setPixmap(image.scaled(width,height,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self._preview_key=preview_key

    def open_source(self, url):
        from .private_browser import open_private
        try:
            open_private(url)
        except (ValueError, RuntimeError) as error:
            QMessageBox.information(self, '无痕浏览', str(error))

    def fullscreen_stills(self,item):
        if item is None:return
        from .catalog_ui import StillViewer
        viewer=StillViewer([self.still_gallery.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.still_gallery.count())],self.still_gallery.row(item),self);viewer.exec()

    def view_cover(self):
        if not self.poster_path:
            self.window.status.setText('此影片暂无封面，可从 NFO 补充或通过插件刮削。');return
        from .catalog_ui import StillViewer
        viewer=StillViewer([self.poster_path],parent=self,title='封面')
        viewer.exec();viewer.deleteLater()

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
        if hasattr(self,'expanded_still'):self.expanded_still.hide();self.expanded_still.clear();self.expanded_still_path=None
        if hasattr(self,'poster_path'):self.render_artwork()

    def select_episode(self, item):
        from .artwork import still_paths
        file=item.data(Qt.ItemDataRole.UserRole)
        self.episode_overview.setText(file.get('overview',''))
        self.set_stills(file.get('stills') or still_paths(self.work),'单集剧照' if file.get('stills') else '剧照')
        self.gallery_status.setText(f'已载入 {self.still_gallery.count()} 张剧照 · 点击放大' if self.still_gallery.count() else '此集暂无可显示的剧照。')

    def show_still(self, item):
        path=item.data(Qt.ItemDataRole.UserRole)
        if getattr(self,'expanded_still_path',None)==path:return
        first=not hasattr(self,'expanded_still') or self.expanded_still.isHidden()
        if not hasattr(self,'expanded_still'):
            self.expanded_still=QLabel();self.expanded_still.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.expanded_still.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            self.expanded_still.setMinimumWidth(0);self.expanded_still.setStyleSheet('background:#080808;')
            self.expanded_still.setFixedHeight(max(200,min(720,round((self.width()-68)*9/16))))
            self.layout().insertWidget(self.layout().indexOf(self.still_gallery)+1,self.expanded_still)
        self.expanded_still_path=path
        if self.expanded_still.pixmap().isNull():self.expanded_still.setText('正在加载剧照…')
        self.render_artwork();self.expanded_still.show()
        if first and self.window.details_scroll is not None:
            QTimer.singleShot(0,lambda:self.window.details_scroll.ensureWidgetVisible(self.expanded_still,0,16) if self.window.detail_page is self else None)

    def choose_download_folder(self):
        from .downloads import download_folder,set_download_folder
        path=QFileDialog.getExistingDirectory(self,'选择此作品的下载目录',str(download_folder(self.library,self.work_id)))
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
        dialog.resize(650, 650)
        layout = QVBoxLayout(dialog)
        title = QLineEdit(self.work['title'])
        layout.addWidget(label('影片名称'))
        layout.addWidget(title)
        year = QSpinBox()
        year.setRange(0, 2100)
        year.setSpecialValueText('未知')
        year.setValue(self.work['year'] or 0)
        layout.addWidget(label('年份'))
        layout.addWidget(year)
        tags = QLineEdit(', '.join(self.work['metadata'].get('tags', [])))
        layout.addWidget(label('标签（逗号分隔）'))
        layout.addWidget(tags)
        overview = QPlainTextEdit(self.work['metadata'].get('overview', ''))
        layout.addWidget(label('简介'))
        layout.addWidget(overview)
        actors = QPlainTextEdit(json.dumps(self.work['metadata'].get('actors', []), ensure_ascii=False, indent=2))
        actors.setPlaceholderText('[{"name":"姓名","gender":"female","aliases":[],"photo":"https://…"}]')
        layout.addWidget(label('演员资料（JSON；gender: female / male / unknown）'))
        layout.addWidget(actors)
        row = QHBoxLayout()
        locks = {}
        for field in ['title', 'year', 'tags', 'overview', 'actors', 'poster']:
            check = QCheckBox(field)
            check.setChecked(field in self.work['locked'])
            row.addWidget(check)
            locks[field] = check
        layout.addWidget(label('锁定字段'))
        layout.addLayout(row)
        def save():
            try:
                people = json.loads(actors.toPlainText())
                if not isinstance(people, list) or any(not isinstance(a, dict) or not a.get('name') or a.get('gender', 'unknown') not in {'female','male','unknown'} for a in people):
                    raise ValueError('演员须为数组，每项包含 name 和有效 gender')
                if not title.text().strip():
                    raise ValueError('名称不能为空')
                self.library.edit_metadata(self.work_id, {'title': title.text().strip(), 'year': year.value() or None,
                    'tags': [s.strip() for s in tags.text().replace('，', ',').split(',') if s.strip()], 'overview': overview.toPlainText(), 'actors': people},
                    [k for k, c in locks.items() if c.isChecked()])
                dialog.accept()
                self.accept()
                self.window.refresh()
            except Exception as exc:
                QMessageBox.warning(dialog, '资料未保存', str(exc))
        layout.addWidget(button('保存资料', save, True))
        dialog.exec()

    def merge_duplicate(self):
        candidates = [w for w in self.library.query({'kinds':[self.work['kind']], 'local':False}) if w['id'] != self.work_id]
        if not candidates:
            QMessageBox.information(self, '合并作品', '没有其他相同类型的作品可合并。')
            return
        names = [f"#{w['id']} · {w['title']} ({w['year'] or '未知年份'}) · {len(w['files'])} 个文件" for w in candidates]
        choice, ok = QInputDialog.getItem(self, '选择重复作品', '将其文件、来源和历史合并到当前作品', names, 0, False)
        if not ok:
            return
        source = candidates[names.index(choice)]
        if QMessageBox.question(self, '确认合并', f"将“{source['title']}”合并到“{self.work['title']}”？\n不会移动或删除视频文件。重复的个人评分以当前作品为准，文件、来源与历史归为一个作品，随机队列也会去重。") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.library.merge_works(source['id'], self.work_id)
            self.window.refresh()
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, '合并失败', str(exc))

    def scrape(self):
        available = [p for p in Plugins(self.library).installed() if p['config'].get('enabled') and ('search' in p['capabilities'] or 'detail' in p['capabilities'])]
        if not available:
            QMessageBox.information(self, '刮削插件', '请先在设置中安装并启用支持搜索或详情解析的插件。')
            return
        name, ok = QInputDialog.getItem(self, '刮削来源', '按优先级选择插件', [p['name'] for p in available], 0, False)
        if not ok:
            return
        plugin = next(p for p in available if p['name'] == name)
        text, ok = QInputDialog.getText(self, '匹配影片', '输入关键词或完整详情页 URL', text=self.work['title'])
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
                self.library.task(__import__('uuid').uuid4().hex, 'match', 'pending', {'work_id': self.work_id, 'plugin': plugin['id']}, error='未找到候选，请手动指定详情页')
                QMessageBox.information(self.window, '待处理', '未找到候选，已记录到任务列表。')
                return
            from .matching import CandidatePicker, apply_match
            picker = CandidatePicker(self.library.directory, plugin['id'], results, self.window)
            accepted = picker.exec()
            candidate = picker.selection()
            picker.deleteLater()
            if accepted and candidate is not None:
                work_id = self.work_id
                self.window.run_job('保存刮削资料与图片',
                    lambda lib, progress: apply_match(lib, plugin, operation, candidate, work_id),
                    lambda result: self.window.reload_details(work_id))
        self.window.run_job('搜索刮削来源', lambda lib, p: Plugins(lib).run(plugin['id'], operation, **({'url': text.strip()} if operation == 'detail' else {'query': text.strip()})), complete)


    def organize(self):
        target = QFileDialog.getExistingDirectory(self, '选择整理目标根目录')
        if not target:
            return
        # Hashing / planning runs off the UI thread for large video files.
        def ready(pairs):
            if not pairs:
                return
            dialog = QMessageBox(self.window)
            dialog.setWindowTitle('确认文件整理')
            dialog.setText(f'将移动 {len(pairs)} 个视频及关联文件。复制并校验成功后才删除原文件。')
            dialog.setDetailedText('\n'.join(f"{p['source']}\n→ {p['target']}" for p in pairs))
            dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            if dialog.exec() == QMessageBox.StandardButton.Ok:
                self.window.run_job('整理文件', lambda lib, progress: execute_move(lib, pairs))
        self.window.run_job('检查文件整理计划', lambda lib, p: plan_move(lib, self.work_id, target), ready)
        self.accept()

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
            self.window.run_job('重新截取封面', generate)
            self.accept()


class MainWindow(QMainWindow):
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
        self.job_queue=[];self.jobs_paused=False;self._job_functions={}
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
        self.drawer = QFrame()
        self.drawer.setObjectName('sidebar')
        self.drawer.setFixedWidth(220)
        menu_button = button('☰', lambda: self.drawer.setVisible(not self.drawer.isVisible()))
        menu_button.setObjectName('headerButton')
        menu_button.setToolTip('媒体库与工具')
        header_layout.addWidget(menu_button)
        self.navigation_back=ActionButton('返回上一页','back',self.back_navigation).icon_only()
        self.navigation_back.hide();header_layout.addWidget(self.navigation_back)
        header_layout.addWidget(label('Lumen', 'brand'))
        header_layout.addStretch()
        for text, action in [('首页', lambda: self.navigate('home')), ('为我推荐',lambda:self.navigate('recommend')),('影片发现',lambda:self.navigate('discover')),('收藏', self.open_favorites)]:
            control = button(text, action)
            control.setObjectName('headerButton')
            header_layout.addWidget(control)
        header_layout.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索媒体库')
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(240)
        self.search.returnPressed.connect(self.search_all)
        header_layout.addWidget(self.search)
        header_layout.addWidget(ActionButton('随机播放','shuffle',self.show_queue).icon_only())
        utilities=ActionButton('工具','more').icon_only();utility_menu=QMenu(utilities)
        utility_menu.addAction('从本地 NFO 补充图片…',lambda:self.import_nfo_artwork());utility_menu.addAction('导入与刮削任务',self.show_tasks);utility_menu.addAction('检查软件更新…',self.check_updates);utilities.setMenu(utility_menu);header_layout.addWidget(utilities)
        utility_menu.addAction('目录监控与媒体库体检…',self.library_tools)
        header_layout.addWidget(ActionButton('设置','settings',self.settings).icon_only())
        root.addWidget(header)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(body, 1)
        nav = QVBoxLayout(self.drawer)
        nav.setContentsMargins(6, 20, 6, 18)
        self.nav_buttons = {}
        for key, title in [('home','首页'),('recommend','为我推荐'),('discover','影片发现'),('movie','电影'),('series','电视剧'),('vr','VR电影'),('fans','Fans'),('other','其他'),('stats','观影统计')]:
            control = button(title, lambda checked=False, key=key: self.navigate(key))
            control.setObjectName('nav')
            control.setCheckable(True)
            self.nav_buttons[key] = control
            nav.addWidget(control)
        nav.addStretch()
        nav.addWidget(button('导入与刮削任务', self.show_tasks))
        nav.addWidget(button('设置', self.settings))
        body.addWidget(self.drawer)
        self.drawer.hide()
        self.pages = QStackedWidget()
        self.browse_page = QWidget()
        self.pages.addWidget(self.browse_page)
        self.detail_page = None
        self.details_scroll = None
        body.addWidget(self.pages, 1)
        main = QVBoxLayout(self.browse_page)
        main.setContentsMargins(42, 18, 42, 12)
        main.setSpacing(10)
        tools_row = QHBoxLayout()
        self.import_control = ActionButton('添加媒体','plus',self.import_dialog)
        self.filter_control = ActionButton('筛选','filter',self.filter_dialog)
        self.heading = label('', 'heading')
        tools_row.addWidget(self.heading)
        tools_row.addStretch()
        tools_row.addWidget(self.filter_control)
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
        self.toolbar = QHBoxLayout()
        self.toolbar.addWidget(ActionButton('随机播放','shuffle',self.shuffle))
        lists=ActionButton('片单','bookmark');list_menu=QMenu(lists);list_menu.addAction('保存当前筛选为片单…',self.save_list);list_menu.addAction('打开片单…',self.load_list);lists.setMenu(list_menu);self.toolbar.addWidget(lists)
        self.toolbar.addWidget(button('打开智能片单', self.load_list))
        self.toolbar.addWidget(button('刷新新片', self.discover))
        self.toolbar.addStretch()
        self.view_mode = QComboBox()
        self.view_mode.addItem('海报', 'poster')
        self.view_mode.addItem('缩略图', 'thumbnail')
        self.view_mode.setCurrentIndex(max(0, self.view_mode.findData(self.library.setting('view_mode', 'poster'))))
        self.view_mode.currentIndexChanged.connect(self.change_view_mode)
        self.toolbar.addWidget(self.view_mode)
        self.catalog_sort=QComboBox()
        for text,key in [('入库时间','added'),('名称','title'),('年份','year'),('个人评分','rating'),('时长','duration')]:self.catalog_sort.addItem(text,key)
        self.catalog_sort.setCurrentIndex(max(0,self.catalog_sort.findData(self.library.setting('catalog_sort','added'))))
        self.catalog_sort.currentIndexChanged.connect(self.change_catalog_sort);self.toolbar.addWidget(self.catalog_sort)
        self.catalog_direction=QPushButton('降序' if self.library.setting('catalog_descending',True) else '升序')
        self.catalog_direction.clicked.connect(self.flip_catalog_sort);self.toolbar.addWidget(self.catalog_direction)
        self.batch_select=QPushButton('多选');self.batch_select.setCheckable(True);self.batch_select.toggled.connect(self.select_catalog_mode);self.toolbar.addWidget(self.batch_select)
        from .catalog_ui import batch_menu,relocate
        self.batch_action=button('批量操作',lambda:batch_menu(self));self.toolbar.addWidget(self.batch_action)
        self.relocate_action=button('修复路径',lambda:relocate(self));self.toolbar.addWidget(self.relocate_action)
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
        self.source_filter = QComboBox()
        self.category_filter = QComboBox()
        self.category_filter.addItem('全部分类', '')
        from .discovery_ui import DiscoveryPanel
        self.discovery_panel=DiscoveryPanel(self)
        main.addWidget(self.discovery_panel)
        main.addLayout(self.toolbar)
        main.addWidget(self.home_page, 1)
        self.splitter = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('文件夹')
        self.tree.itemClicked.connect(self.folder_selected)
        self.splitter.addWidget(self.tree)
        self.cards = PosterList(self.play_work)
        self.cards.favoriteRequested.connect(self.toggle_favorite)
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
        self.job_area=QWidget();self.job_area.setFixedHeight(40)
        job_row=QHBoxLayout(self.job_area);job_row.setContentsMargins(42,0,42,0);job_row.setSpacing(12)
        self.job_progress = QProgressBar();self.job_progress.setFixedHeight(8);self.job_progress.setTextVisible(False);self.job_progress.setMinimumWidth(0)
        self.job_progress.hide()
        job_row.addWidget(self.job_progress,1)
        self.job_counter=ElidedLabel();self.job_counter.setFixedWidth(100);self.job_counter.hide();job_row.addWidget(self.job_counter)
        self.cancel_job = button('停止处理队列',self.stop_jobs)
        self.cancel_job.setFixedWidth(150);self.cancel_job.setStyleSheet('padding: 3px 10px; min-height: 22px;')
        self.cancel_job.hide()
        job_row.addWidget(self.cancel_job)
        for control in (self.job_progress,self.job_counter,self.cancel_job):
            policy=control.sizePolicy();policy.setRetainSizeWhenHidden(True);control.setSizePolicy(policy)
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
        self.watch_scheduler=QTimer(self);self.watch_scheduler.setInterval(10000);self.watch_scheduler.timeout.connect(self.schedule_watched);self.watch_scheduler.start()
        with self.library.db:
            self.library.db.execute("UPDATE tasks SET status='cancelled',error='应用重启，未完成任务可重试' WHERE kind='background' AND status IN ('running','paused','queued')")

    def library_tools(self):
        from .library_tools_ui import LibraryTools
        LibraryTools(self).exec()

    def playback_refreshed(self):
        self.refresh()
        if self.detail_page:self.detail_page.sync_personal();self.detail_page.refresh_bookmarks()

    def schedule_watched(self):
        if self.jobs or self.job_queue or self.jobs_paused or self._closing or not any(row.get('enabled',True) for row in self.library.setting('watched_folders',[])):return
        from .media_tools import watch_folders
        self.run_job('目录自动监控',lambda lib,p:watch_folders(lib,p,cancelled=p.cancelled),quiet=True)

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

    def start_queued_jobs(self):
        if self._closing or self.jobs_paused:return
        limit=max(1,min(3,int(self.library.setting('background_concurrency',1))))
        while self.job_queue and len(self.jobs)<limit:
            title,function,callback,identifier,quiet=self.job_queue.pop(0)
            self.run_job(title,function,callback,_identifier=identifier,quiet=quiet)

    def schedule_media(self):
        if self.jobs or self.job_queue or self.jobs_paused or self._closing:
            return
        pending = self.library.db.execute('SELECT COUNT(*) FROM import_cache WHERE pending IN (1,2)').fetchone()[0]
        if pending:
            self.run_job(f'后台补充媒体信息 · 剩余 {pending} 个', lambda lib, progress: lib.enrich_pending(progress, cancelled=progress.cancelled))

    def open_favorites(self):
        self.navigate('home')
        self.tabs.setCurrentIndex(2)
        self.filters = {'favorite': True}
        self.heading.setText('收藏')
        self.refresh()

    def navigate(self, section, preserve_history=False):
        self._close_details()
        if not preserve_history:self.navigation_history.clear();self._restore_browse_state=None
        self.navigation_back.setVisible(bool(self.navigation_history))
        self.drawer.hide()
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
        for key, b in self.nav_buttons.items():
            b.setChecked(key == section)
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
        value=not self.library.setting('catalog_descending',True);self.library.set_setting('catalog_descending',value)
        self.catalog_direction.setText('降序' if value else '升序');self.filters.pop('descending',None);self.refresh()

    def select_catalog_mode(self,enabled):
        self.cards.setProperty('batchMode',enabled)
        self.cards.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection if enabled else QAbstractItemView.SelectionMode.SingleSelection)
        self.cards.clearSelection()

    def change_view_mode(self):
        self.library.set_setting('view_mode', self.view_mode.currentData())
        if self.view_mode.currentData() == 'thumbnail':
            for file in self.library.db.execute('SELECT f.id,f.digest FROM files f JOIN import_cache c ON c.file_id=f.id WHERE c.pending=0').fetchall():
                if not (self.library.directory / 'cache' / (file['digest'] + '.jpg')).exists():
                    with self.library.db:
                        self.library.db.execute('UPDATE import_cache SET pending=2 WHERE file_id=?',(file['id'],))
        self.refresh()

    def card_data(self, data, landscape=False):
        record = {key:data[key] for key in ('id','kind','title','name','year','thumbnail','photo_cache','average','count','rated','favorite','watchlist','rating','_subtitle','reasons') if key in data}
        if 'work_ids' in data:record['work_ids']=[]
        record['files']=[{key:file[key] for key in ('id','work_id','path','digest','duration','position','completed','season','episode') if key in file} for file in data.get('files',[])]
        record['sources']=[{'rating':source.get('rating')} for source in data.get('sources',[])]
        record['_landscape'] = bool(data.get('kind')) and (landscape or self.view_mode.currentData() == 'thumbnail')
        if record['_landscape']:
            for file in data.get('files', []):
                local=data.get('metadata',{}).get('nfo_thumbnails',{}).get(str(file['id']))
                frame = Path(local) if local else self.library.directory / 'cache' / (file['digest'] + '.jpg')
                if frame.exists():
                    record['_cover'] = str(frame)
                    break
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
                self.cards.setEnabled(False);self.home_page.setEnabled(False)
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
        actresses = self.section == 'movie' and self.subtab == 1
        home=self.section=='home' and self.subtab==0
        for index in range(4):
            self.toolbar.itemAt(index).widget().setVisible((self.section == 'discover') if index == 3 else index!=2 and self.section not in {'discover','stats'})
        self.view_mode.setVisible(not actresses and self.section != 'stats')
        for control in [self.catalog_sort,self.catalog_direction]:control.setVisible(not actresses and self.section not in {'stats','discover','recommend'} and not home)
        self.batch_select.setVisible(not actresses and self.section not in {'stats','discover'} and not home)
        self.batch_action.setVisible(not actresses and self.section not in {'stats','discover'} and not home)
        self.relocate_action.setVisible(self.section in KINDS)
        self.actor_min.setVisible(actresses)
        self.actor_sort.setVisible(actresses)
        self.actor_photo_action.setVisible(actresses)
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
                items = [w for w in items if any(f['position'] > 0 and not f['completed'] for f in w['files'])]
            elif self.section == 'home' and self.subtab == 3:
                items = [w for w in items if w['watchlist']]
        view_key=json.dumps([self.section,self.subtab,self.effective_filters(),self.discovery_panel.request_fields() if self.section=='discover' else {},self.actor_min.currentData(),self.actor_sort.currentData(),self.view_mode.currentData()],sort_keys=True,ensure_ascii=False)
        preserve=view_key==getattr(self,'_rendered_view_key',None);self._rendered_view_key=view_key
        self.current_items = items
        count=min(len(items),max(60,self.display_count) if preserve else 60)
        update_poster_items(self.cards,[self.card_data(item) for item in items[:count]],preserve)
        self.display_count=self.cards.count()
        self.subtitle.setText(f"{len(items)} {'位女演员' if actresses else '部作品'}  ·  " + ('个人评分的算术平均 · 未评分不计入' if actresses else '点击查看详情 · 右键快速播放'))
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
        self.heading.setText(state['heading'])
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

    def card_menu(self, position):
        item = self.cards.itemAt(position)
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
        if data.get('kind') in {'movie', 'vr'}:
            target = 'movie' if data['kind'] == 'vr' else 'vr'
            menu.addAction('移至' + KINDS[target], lambda: self.change_movie_kind(data['id'], target))
        if data.get('kind'):
            menu.addAction('标记已看',lambda:self.catalog_watch(data['id'],'completed'))
            menu.addAction('标记未看 / 重置进度',lambda:self.catalog_watch(data['id'],'unwatched'))
            menu.addAction('从头播放',lambda:self.catalog_restart(data['id']))
            menu.addAction('加入播放队列',lambda:self.library.edit_queue([*self.library.setting('queue',{'ids':[]})['ids'],data['id']]))
            menu.addAction('仅移出媒体库…',lambda:self.remove_catalog_work(data['id']))
        menu.exec(self.cards.mapToGlobal(position))

    def scrape_actor_photo(self):
        item=self.cards.currentItem();record=item.data(Qt.ItemDataRole.UserRole) if item else {}
        from .actor_ui import show_actor_scraper
        show_actor_scraper(self,record.get('name',''))

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
        if self.section not in {'recommend','discover'}:
            self.navigate('home')
            self.tabs.setCurrentIndex(2)
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
                if self.section not in {'discover','recommend'}:
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
        lists = dict(self.library.db.execute('SELECT name,filters FROM lists'))
        if not lists:
            QMessageBox.information(self, '智能片单', '尚未保存片单。')
            return
        name, ok = QInputDialog.getItem(self, '智能片单', '选择片单', list(lists), 0, False)
        if ok:
            self.navigate('home')
            self.tabs.setCurrentIndex(2)
            self.filters = json.loads(lists[name])
            self.search.setText(self.filters.get('query', ''))
            self.refresh()

    def import_nfo_artwork(self, work_id=None):
        dialog=QDialog(self);dialog.setWindowTitle('从资源目录的 NFO 补充图片');dialog.resize(650,260)
        form=QFormLayout(dialog)
        current=self.library.work(work_id) if work_id else None
        initial=str(Path(current['files'][0]['path']).parent) if current and current['files'] else self.library.setting('artwork_folder','')
        path=QLineEdit(initial)
        browse=button('选择目录…',lambda:path.setText(QFileDialog.getExistingDirectory(dialog,'选择包含 NFO 和图片的资源目录',path.text()) or path.text()))
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

    def import_path(self, path=None):
        if self._closing:return
        from .import_ui import ImportDialog
        dialog=getattr(self,'import_form',None)
        if dialog is None:dialog=self.import_form=ImportDialog(self)
        if path:dialog.path.setText(str(path))
        if not dialog.isVisible():
            dialog.kind.setCurrentIndex(max(0,dialog.kind.findData(self.section if self.section in KINDS else 'movie')))
            dialog.show()
        if dialog.browser is not None and dialog.browser.isVisible():dialog.browser.raise_();dialog.browser.activateWindow();return
        dialog.raise_();dialog.activateWindow()

    def start_import(self,path,kind):
        origin=(self.section,self.subtab)
        def complete(result):
            self.status.setText(f"导入 {result['imported']} · NFO 更新 {result.get('nfo_updated',0)} · 重复 {result['duplicates']} · 失败 {len(result['errors'])} · 警告 {len(result['warnings'])}")
            if self.detail_page is None and (self.section,self.subtab)==origin and self.section!=kind:self.navigate(kind)
            if kind in {'movie','series','vr'}:
                self.auto_scrape_import(path, kind)
        self.run_job('快速导入 · 时长与缺失图片稍后补充', lambda lib, p: lib.import_folder(path, kind, p, fast=True, cancelled=p.cancelled), complete)

    def auto_scrape_import(self, path, kind):
        if kind not in {'movie','series','vr'}:return
        config = self.library.setting('partition:' + kind, {})
        plugin_id = config.get('plugin')
        if not plugin_id:
            return
        def scrape(lib, progress):
            plugin = Plugins(lib)
            works = lib.query({'kinds':[kind], 'folder':str(Path(path).resolve())})
            for i, w in enumerate(works):
                if w['metadata'].get('nfo_fields'):
                    progress(i+1, len(works), w['title'])
                    continue
                try:
                    candidates = plugin.run(plugin_id, 'search', query=w['title'])
                    matches = [m for m in candidates if m.get('kind','movie') == kind and m['title'].casefold() == w['title'].casefold() and (not w['year'] or m.get('year') == w['year'])]
                    if len(matches) != 1:
                        raise ValueError(f'匹配不唯一（{len(candidates)} 个候选），请在详情中确认')
                    plugin.merge(plugin_id, matches[0], w['id'])
                    if config.get('destination'):
                        execute_move(lib, plan_move(lib, w['id'], config['destination']))
                except Exception as exc:
                    lib.task(__import__('uuid').uuid4().hex, 'match', 'pending', {'work_id':w['id'], 'plugin':plugin_id}, error=str(exc))
                progress(i+1, len(works), w['title'])
        self.run_job('自动匹配与分区整理', scrape)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(Path(u.toLocalFile()).is_dir() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        folders = [u.toLocalFile() for u in event.mimeData().urls() if Path(u.toLocalFile()).is_dir()]
        if folders:
            self.import_path(folders[0])
            if len(folders) > 1:
                self.status.setText('本次导入第一个文件夹；其余文件夹可在完成后继续拖入。')

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
        self.job_queue.clear()

    def run_job(self, title, function, callback=None, _identifier=None, quiet=False):
        if self._closing:
            return
        identifier=_identifier or uuid.uuid4().hex
        self._job_functions[identifier]=(title,function,callback,quiet)
        if len(self._job_functions)>32:self._job_functions.pop(next(iter(self._job_functions)))
        if self.jobs_paused or len(self.jobs)>=self.library.setting('background_concurrency',1):
            if len(self.job_queue)>=100:
                self.status.setText('后台队列已满，请等待部分任务完成');return
            self.job_queue.append((title,function,callback,identifier,quiet))
            if not quiet:self.task_journal.record(identifier,'background','queued',{'title':title})
            self.status.setText(f'已排队：{title} · 等待 {len(self.job_queue)} 项')
            return
        if not quiet:self.task_journal.record(identifier,'background','running',{'title':title})
        if not quiet:self.status.setText(title + '…')
        self.job_progress.setRange(0, 0)
        if not quiet:self.job_progress.show();self.job_counter.show();self.job_counter.setText('准备中')
        self.cancel_job.setEnabled(True)
        self.cancel_job.setVisible(not quiet)
        job = Job(self.library.directory, function, self)
        job.task_identifier=identifier
        job.budget=self.task_budget
        self.jobs.append(job)
        last_refresh = [time.monotonic()]
        started=time.monotonic();last_saved=[0];last_counter=[started,0]
        def show_progress(done, total, message):
            if job not in self.jobs:return
            self.job_progress.show();self.job_counter.show();self.cancel_job.show()
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
            self.job_progress.setVisible(bool(self.jobs));self.cancel_job.setVisible(bool(self.jobs))
            self.job_counter.setVisible(bool(self.jobs))
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
            filters = self.effective_filters()
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
            self.run_job('定期发现新片', lambda lib, p: self.refresh_plugins(lib, due))

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
        dialog.setWindowTitle('任务与诊断')
        layout = QVBoxLayout(dialog)
        log_row=QHBoxLayout();log_path=ElidedLabel('日志目录：'+str(self.library.directory))
        log_path.setToolTip(str(self.library.directory));log_row.addWidget(log_path,1)
        log_row.addWidget(button('复制日志路径',lambda:QApplication.clipboard().setText(str(self.library.directory))))
        log_row.addWidget(button('打开日志目录',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.directory)))))
        layout.addLayout(log_row)
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
            run_background(self,lambda job:tasks.snapshot(self.library.directory,page[0]*100),ready,failed)
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
                states={'queued':'排队中','running':'进行中','paused':'已暂停','importing':'入库中','failed':'失败','partial':'部分完成','done':'已完成','cancelled':'已停止','external':'外部工具处理'}
                kinds={'import':'导入','media':'补充媒体','scrape':'刮削','download':'HTTP 下载','download-library':'下载并入库','match':'匹配确认','move':'文件整理','background':'后台处理'}
                for column,text in enumerate([payload.get('title',kinds.get(task['kind'],task['kind'])),states.get(state,state),task['updated'][:19],detail]):
                    text=str(text).replace('\n',' ')[:2000]
                    item=table.item(index,column)
                    if item is None:item=QTableWidgetItem();table.setItem(index,column,item)
                    if item.text()!=text:item.setText(text);item.setToolTip(text)
                    if column==1:item.setForeground(QColor('#e98383' if state in {'failed','partial'} else '#6bc9a5' if state=='done' else '#00a4dc' if state in {'running','importing'} else '#e7c567' if state=='paused' else '#cccccc'))
                if task['id']==selected:table.selectRow(index)
            bar.setValue(position);table.setUpdatesEnabled(True)
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
                if queued[3]==identifier:self.job_queue.remove(queued);self.task_journal.record(identifier,'background','cancelled',{'title':queued[0]});reload();return
        layout.addWidget(button('停止选中后台任务',cancel_selected))
        def inspect_task():
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
                destination,_=QFileDialog.getSaveFileName(detail,'导出完整任务记录',identifier+'.json','JSON (*.json)',options=QFileDialog.Option.DontUseNativeDialog)
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
                self.run_job('恢复文件整理', lambda lib, p: execute_move(lib, task_id=task['id']))
            elif task['kind'] == 'import':
                dialog.accept()
                candidates=task.get('candidates') or None
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
        self._closing = True
        self.discovery_images.stop()
        if getattr(self,'import_form',None):self.import_form.reject()
        self.watch_scheduler.stop();self.remote.timer.stop();self.remote.clear()
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
                job.requestInterruption()
            event.ignore()
            if not self.discovery_images.idle:QTimer.singleShot(100,self.close)
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
                    self.discovery_images.resume()
                    for timer in (self.scheduler,self.media_scheduler,self.watch_scheduler,self.remote.timer):timer.start()
                    self.status.setText('已取消退出，播放记录将在后台重试保存')
                else:QTimer.singleShot(100,self.close)
                return
        self.scheduler.stop()
        self.media_scheduler.stop()
        if self.lan_server:
            self.lan_server.stop()
        self.task_journal.stop()
        self.library.close()
        event.accept()
        if getattr(self,'_update_pending',False):QApplication.instance().quit()
