from __future__ import annotations
import json
from html import escape
from pathlib import Path
import time
import traceback
from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer, QUrl, QRect
from PySide6.QtGui import QPixmap, QIcon, QColor, QPainter, QFont, QDesktopServices, QPixmapCache, QLinearGradient, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
 QGridLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
 QFileDialog, QMessageBox, QInputDialog, QListWidget, QListWidgetItem, QAbstractItemView, QTreeWidget,
 QTreeWidgetItem, QSplitter, QTabBar, QScrollArea, QPlainTextEdit, QTableWidget, QTableWidgetItem,
 QHeaderView, QStackedWidget, QProgressBar, QStyledItemDelegate, QStyle, QMenu, QCompleter)
from .core import Library, thumbnail, tool, ImportCancelled
from .plugins import Plugins
from .files import plan_move, execute_move
from .player import Player
from .presentation import rating_text
from .theme import STYLE

KINDS = {'movie': '电影', 'series': '电视剧', 'vr': 'VR电影', 'other': '其他'}


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
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


class Job(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(object, object, str)

    def __init__(self, directory, function, parent=None):
        super().__init__(parent)
        self.directory, self.function = directory, function

    def run(self):
        library = Library(self.directory)
        try:
            def report(done, total, message):
                self.progress.emit(done, total, message)
            report.cancelled = self.isInterruptionRequested
            self.done.emit(self.function(library, report))
        except ImportCancelled:
            self.done.emit({"cancelled":True})
        except Exception as exc:
            self.failed.emit(str(exc))
            with (self.directory / 'diagnostics.log').open('a', encoding='utf-8') as stream:
                traceback.print_exc(file=stream)
        finally:
            library.close()


class PosterList(QListWidget):
    def __init__(self, play, parent=None):
        super().__init__(parent)
        self.play = play

    def wheelEvent(self,event):
        if not self.isWrapping():
            from .scrolling import route_vertical_wheel
            if route_vertical_wheel(self,event):return
        super().wheelEvent(event)

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item and event.button() == Qt.MouseButton.LeftButton:
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            rect = self.visualItemRect(item).adjusted(8, 8, -8, -82)
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
        pixmap=image_cache().request(cover,image_rect.size()*2)
        if not pixmap.isNull():
            image = pixmap.scaled(image_rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(image_rect.x()+(image_rect.width()-image.width())//2, image_rect.y()+(image_rect.height()-image.height())//2, image)
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
                painter.setPen(QColor('white'))
                painter.setFont(QFont('Segoe UI',18))
                painter.drawText(QRect(center.x()-22,center.y()-24,48,48),Qt.AlignmentFlag.AlignCenter,'▶')
        files = data.get('files',[])
        unfinished = next((f for f in files if f.get('position',0)>0 and not f.get('completed')),None)
        if unfinished and unfinished.get('duration'):
            progress = min(1,unfinished['position']/unfinished['duration'])
            painter.fillRect(QRect(image_rect.x(),image_rect.bottom()-4,image_rect.width(),5), QColor(0,0,0,160))
            painter.fillRect(QRect(image_rect.x(),image_rect.bottom()-4,int(image_rect.width()*progress),5), QColor('#00a4dc'))
        if data.get('kind') == 'series' and files:
            badge = QRect(image_rect.right()-36,image_rect.top()+7,28,28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#00a4dc'))
            painter.drawEllipse(badge)
            painter.setPen(QColor('white'))
            painter.setFont(QFont('Segoe UI',10))
            painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,str(len(files)))
        painter.setClipping(False)
        if selected:
            painter.setPen(QColor('#00a4dc'))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(image_rect,3,3)
        painter.setPen(QColor('#eeeeee'))
        painter.setFont(QFont('Segoe UI',11))
        title = data.get('title') or data.get('name','')
        painter.drawText(QRect(rect.x(),image_rect.bottom()+7,rect.width(),22),Qt.AlignmentFlag.AlignCenter,painter.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,rect.width()-4))
        painter.setPen(QColor('#999999'))
        painter.setFont(QFont('Segoe UI',10))
        subtitle = data.get('_subtitle') or str(data.get('year') or '')
        if data.get('kind'):
            subtitle += '  ·  ' + ('♥ 喜欢' if data.get('favorite') else '♡ 未喜欢')
        painter.drawText(QRect(rect.x(),image_rect.bottom()+30,rect.width(),18),Qt.AlignmentFlag.AlignCenter,painter.fontMetrics().elidedText(subtitle,Qt.TextElideMode.ElideRight,rect.width()-4))
        if data.get('kind'):
            painter.setPen(QColor('#e5c25b'))
            painter.drawText(QRect(rect.x(),image_rect.bottom()+51,rect.width(),20),Qt.AlignmentFlag.AlignCenter, rating_text(data))
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

    def pathFromIndex(self, index):
        value = super().pathFromIndex(index)
        entered = self.combo.entered.replace('，', ',')
        return entered.rsplit(',', 1)[0] + ', ' + value if ',' in entered else value


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
        self.lineEdit().setPlaceholderText('输入搜索或下拉选择' + ('；多个标签以逗号分隔' if multiple else '；留空不限'))

    def remember(self, value):
        self.entered = value

    def chosen(self, value):
        if self.multiple and ',' in self.entered.replace('，', ',') and ',' not in value:
            prefix = self.entered.replace('，', ',').rsplit(',', 1)[0]
            self.setEditText(prefix + ', ' + value)
        self.entered = self.currentText()

    def text(self):
        return self.currentText().strip()

    def value(self):
        return int(self.text()) if self.text().isdigit() else 0


class FilterDialog(QDialog):
    def __init__(self, filters, parent=None, options=None):
        super().__init__(parent)
        options = options or {}
        self.setWindowTitle('组合筛选 · 应用于完整媒体库')
        self.resize(520, 600)
        layout = QFormLayout(self)
        self.query = QLineEdit(filters.get('query', ''))
        layout.addRow('关键词 / 别名 / 路径', self.query)
        self.types = {}
        row = QHBoxLayout()
        for kind, text in KINDS.items():
            check = QCheckBox(text)
            check.setChecked(kind in filters.get('kinds', KINDS))
            row.addWidget(check)
            self.types[kind] = check
        layout.addRow('媒体分区', row)
        self.fields = {}
        for key, title in [('tags_any','包含任一标签'), ('tags_all','同时包含标签'), ('tags_not','排除标签')]:
            field = FilterCombo(options.get('tags', []), ', '.join(filters.get(key, [])), multiple=True)
            self.fields[key] = field
            layout.addRow(title, field)
        self.numbers = {}
        for key, title, maximum in [('year_min','起始年份',2100), ('year_max','截止年份',2100), ('rating_min','最低个人评分',10), ('rating_max','最高个人评分',10)]:
            if key.startswith('year_'):
                field = FilterCombo(options.get('years', []), filters.get(key) or '')
            else:
                field = QSpinBox()
                field.setRange(0, maximum)
                field.setSpecialValueText('不限')
                field.setValue(filters.get(key) or 0)
            self.numbers[key] = field
            layout.addRow(title, field)
        self.watched = QComboBox()
        for text, value in [('不限', ''), ('已观看', 'yes'), ('未观看', 'no')]:
            self.watched.addItem(text, value)
        self.watched.setCurrentIndex(max(0, self.watched.findData(filters.get('watched', ''))))
        layout.addRow('观看状态', self.watched)
        self.favorite = QCheckBox('仅收藏')
        self.favorite.setChecked(filters.get('favorite', False))
        layout.addRow('', self.favorite)
        self.folder = QLineEdit(filters.get('folder', ''))
        row = QHBoxLayout()
        row.addWidget(self.folder)
        row.addWidget(button('选择', self.choose_folder))
        layout.addRow('目录范围', row)
        self.actor = FilterCombo(options.get('actors', []), filters.get('actor', ''))
        layout.addRow('演员姓名', self.actor)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addRow(controls)

    def accept(self):
        for key in ('year_min', 'year_max'):
            field = self.numbers[key]
            if field.text() and not 1800 <= field.value() <= 2200:
                QMessageBox.information(self, '年份', '请选择或输入 1800–2200 的年份，留空表示不限。')
                return
        if self.numbers['year_min'].value() and self.numbers['year_max'].value() and self.numbers['year_min'].value() > self.numbers['year_max'].value():
            QMessageBox.information(self, '年份', '起始年份不能晚于截止年份。')
            return
        super().accept()

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, '随机 / 筛选目录范围')
        if path:
            self.folder.setText(path)

    def filters(self):
        return {'query': self.query.text(), 'kinds': [k for k, c in self.types.items() if c.isChecked()],
                **{k: [s.strip() for s in f.text().replace('，', ',').split(',') if s.strip()] for k, f in self.fields.items()},
                **{k: f.value() for k, f in self.numbers.items() if f.value()},
                'watched': self.watched.currentData(), 'folder': self.folder.text(), 'actor': self.actor.text(),
                **({'favorite': True} if self.favorite.isChecked() else {})}


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
        outer.addWidget(button('← 返回', self.accept), alignment=Qt.AlignmentFlag.AlignLeft)
        self.setMinimumHeight(760)
        top = QHBoxLayout()
        poster = self.poster = QLabel()
        poster.setFixedSize(210, 315)
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setScaledContents(False)
        poster.setStyleSheet('background: #181818; border: none;')
        self.poster_path=w['thumbnail']
        top.addWidget(poster)
        info = QVBoxLayout()
        heading = label(w['title'], 'heading')
        heading.setWordWrap(True)
        info.addWidget(heading)
        info.addWidget(label(f"{KINDS[w['kind']]}  /  {w['year'] or '年份待补充'}  /  {len(w['files'])} 个视频文件", 'subtitle'))
        def links(values, field):
            widget = QLabel()
            widget.setTextFormat(Qt.TextFormat.RichText)
            widget.setWordWrap(True)
            widget.setText('  ·  '.join(f'<a href="{index}" style="color:#00a4dc;text-decoration:none">{escape(value)}</a>' for index,value in enumerate(values)))
            widget.linkActivated.connect(lambda index: window.search_metadata(field, values[int(index)]))
            info.addWidget(widget)
            return widget
        self.tag_links = links(w['metadata'].get('tags', []), 'tags_all')
        self.actor_links = links([actor['name'] for actor in w['metadata'].get('actors', [])], 'actor')
        if w['metadata'].get('released'):
            info.addWidget(label('上映 / 首播：' + str(w['metadata']['released']), 'subtitle'))
        description = label(w['metadata'].get('overview', '暂无简介。可通过刮削插件补充资料。') if w['kind'] != 'other' else '保留原始目录结构，不进行联网刮削。')
        description.setWordWrap(True)
        info.addWidget(description, 1)
        recommended = next((item for item in window.current_items if item.get('id') == work_id and item.get('reasons')), None)
        if recommended:
            reasons = label('推荐原因：' + '；'.join(recommended['reasons']), 'subtitle')
            reasons.setWordWrap(True)
            info.addWidget(reasons)
        actions = QHBoxLayout()
        play = button('▶  继续播放', lambda: window.play_work(work_id), True)
        play.setEnabled(bool(w['files']))
        actions.addWidget(play)
        actions.addWidget(button('整理文件…', self.organize))
        info.addLayout(actions)
        top.addLayout(info, 1)
        outer.addLayout(top)
        personal = QHBoxLayout()
        if w['kind'] != 'other':
            personal.addWidget(label('个人评分'))
            rating = QSpinBox()
            rating.setRange(0, 10)
            rating.setSpecialValueText('未评分')
            rating.setValue(w['rating'] or 0)
            rating.valueChanged.connect(lambda value: self.personal(rating=value or None))
            personal.addWidget(rating)
        for key, title in [('favorite','喜欢'),('watchlist','想看'),('disliked','不感兴趣')]:
            check = QCheckBox(title)
            check.setChecked(bool(w[key]))
            check.toggled.connect(lambda value, key=key: self.personal(**{key: value}))
            personal.addWidget(check)
        personal.addStretch()
        if w['kind'] != 'other':
            personal.addWidget(button('合并重复作品', self.merge_duplicate))
            personal.addWidget(button('编辑资料 / 锁定', self.edit))
            personal.addWidget(button('刮削…', self.scrape))
        outer.addLayout(personal)
        self.files = QListWidget()
        for f in w['files']:
            title = ((f"S{f['season']:02} E{f['episode']:02}  ·  " if f['season'] is not None and f['episode'] is not None else '待补充季集  ·  ') if w['kind'] == 'series' else '') + (f.get('title') or Path(f['path']).name)
            duration_text = f"{f['duration']/60:.1f} 分钟" if f['duration'] > 0 else "时长待补充"
            item = QListWidgetItem(f"{title}   ·   {duration_text}   ·   上次 {f['position']/60:.1f} 分钟")
            item.setToolTip(f['path'])
            item.setData(Qt.ItemDataRole.UserRole, f)
            self.files.addItem(item)
        self.files.itemDoubleClicked.connect(lambda item: window.play_file(item.data(Qt.ItemDataRole.UserRole)))
        self.files_heading=label('视频文件 / 季与集 · 双击播放', 'subtitle')
        outer.addWidget(self.files_heading)
        outer.addWidget(self.files)
        self.files.setMinimumHeight(90)
        self.files.setMaximumHeight(200)
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
        outer.insertWidget(4,self.still_gallery)
        self.still_gallery.itemClicked.connect(self.show_still)
        self.set_stills(still_paths(w))
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
        self.download_directory_label=label('保存位置：'+str(download_folder(self.library,self.work_id)) if w['kind'] != 'other' else '其他分类不使用插件下载')
        self.download_directory_label.setWordWrap(True)
        outer.addWidget(self.download_directory_label)
        directory_actions=QHBoxLayout()
        directory_actions.addWidget(button('更改本片下载目录…',self.choose_download_folder))
        directory_actions.addWidget(button('恢复分类默认目录',self.reset_download_folder))
        directory_actions.addWidget(button('检查下载文件并入库',self.import_downloads))
        outer.addLayout(directory_actions)
        self.download_directory_label.setVisible(w['kind'] != 'other')
        for index in range(directory_actions.count()):directory_actions.itemAt(index).widget().setVisible(w['kind'] != 'other')
        self.resource_buttons=[]
        for entry in w['metadata'].get('download_url',[]):
            method=entry.get('method',w['metadata'].get('download_method'))
            text=entry.get('description') or ('磁力下载' if method=='magnet' else '直接下载')
            control=button(('磁力 · ' if method=='magnet' else '直链 · ')+text,
                           lambda checked=False,entry=entry:self.start_download(entry))
            self.resource_buttons.append(control);outer.addWidget(control)
        if not self.resource_buttons:
            outer.addWidget(label('来源尚未提供下载资源；可刷新来源详情。','subtitle'))
        self.refresh_resources=button('刷新剧照与下载资源',lambda:self.window.refresh_source_details(self.work_id))
        outer.addWidget(self.refresh_resources)
        outer.addWidget(button('从本地 NFO 补充图片…',lambda:self.window.import_nfo_artwork(self.work_id)))
        if not self.work['files']:
            outer.addWidget(label('此影片尚未入库。查看剧照和下载资源无需先导入视频。','subtitle'))
        bottom = QHBoxLayout()
        bottom.addWidget(button('重新截取封面…', self.recapture))
        bottom.addStretch()
        bottom.addWidget(button('返回媒体库', self.accept))
        outer.addLayout(bottom)
        from .images import image_cache
        image_cache().changed.connect(self.render_artwork)
        self.render_artwork()

    def render_artwork(self):
        from .images import image_cache
        cache=image_cache()
        image=cache.request(self.poster_path,QSize(420,630))
        if not image.isNull():self.poster.setPixmap(image.scaled(self.poster.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        for path in self.backdrop_paths:
            image=cache.request(path,QSize(1400,800))
            if not image.isNull() and image.width()>image.height():self.backdrop=image;break
        for index in range(self.still_gallery.count()):
            item=self.still_gallery.item(index)
            image=cache.request(item.data(Qt.ItemDataRole.UserRole),QSize(576,324))
            if not image.isNull():item.setIcon(QIcon(image))
        self.update()

    def open_source(self, url):
        from .private_browser import open_private
        try:
            open_private(url)
        except (ValueError, RuntimeError) as error:
            QMessageBox.information(self, '无痕浏览', str(error))

    def set_stills(self, paths, prefix='剧照'):
        self.still_gallery.clear()
        for path in dict.fromkeys(paths):
            item=QListWidgetItem(f'{prefix} {self.still_gallery.count()+1}')
            item.setData(Qt.ItemDataRole.UserRole,path)
            self.still_gallery.addItem(item)
        visible=bool(self.still_gallery.count())
        self.gallery_heading.setVisible(visible)
        self.still_gallery.setVisible(visible)
        if hasattr(self,'expanded_still'):self.expanded_still.hide()
        if hasattr(self,'poster_path'):self.render_artwork()

    def select_episode(self, item):
        from .artwork import still_paths
        file=item.data(Qt.ItemDataRole.UserRole)
        self.episode_overview.setText(file.get('overview',''))
        self.set_stills(file.get('stills') or still_paths(self.work),'单集剧照' if file.get('stills') else '剧照')
        self.gallery_status.setText(f'已载入 {self.still_gallery.count()} 张剧照 · 点击放大' if self.still_gallery.count() else '此集暂无可显示的剧照。')

    def show_still(self, item):
        # Expand inside the details page instead of opening a modal dialog.
        if not hasattr(self,'expanded_still'):
            self.expanded_still=QLabel()
            self.expanded_still.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout().insertWidget(self.layout().indexOf(self.still_gallery)+1,self.expanded_still)
        image=QPixmap(item.data(Qt.ItemDataRole.UserRole))
        self.expanded_still.setPixmap(image.scaled(max(320,self.width()-68),720,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        self.expanded_still.show()
        if self.window.details_scroll is not None:
            QTimer.singleShot(0,lambda:self.window.details_scroll.ensureWidgetVisible(self.expanded_still) if self.window.detail_page is self else None)

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
            image = self.backdrop.scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((area.width()-image.width())//2, (area.height()-image.height())//2, image)
            painter.fillRect(area, QColor(0, 0, 0, 165))
            fade = QLinearGradient(0, 100, 0, area.height())
            fade.setColorAt(0, QColor(16,16,16,0))
            fade.setColorAt(1, QColor('#101010'))
            painter.fillRect(area, fade)
            painter.restore()

    def personal(self, **fields):
        self.library.update_personal(self.work_id, **fields)
        self.window.refresh()

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
    def __init__(self, directory=None):
        super().__init__()
        self.library = Library(directory)
        self.lan_server = None
        self.setWindowTitle('Lumen · 私人光影库')
        self.resize(1400, 900)
        self.setMinimumSize(1024, 700)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        self.jobs = []
        self._closing = False
        self._browse_job=None;self._browse_pending=None;self._browse_epoch=0
        self.section, self.subtab = 'home', 0
        self.filters = {}
        self.current_items = []
        self.display_count = 0
        self.random_active = False
        self.player = Player(self.library, self)
        self.player.queueNext.connect(lambda: self.step_playback(1))
        self.player.queuePrevious.connect(lambda: self.step_playback(-1))
        self.player.refreshed.connect(self.refresh)
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
        header_layout.addWidget(label('Lumen', 'brand'))
        header_layout.addStretch()
        for text, action in [('首页', lambda: self.navigate('home')), ('收藏', self.open_favorites)]:
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
        for text, action in [('随机播放', self.show_queue), ('本地 NFO 图片', lambda checked=False:self.import_nfo_artwork()), ('设置', self.settings)]:
            control = button(text, action)
            control.setObjectName('headerButton')
            header_layout.addWidget(control)
        root.addWidget(header)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(body, 1)
        nav = QVBoxLayout(self.drawer)
        nav.setContentsMargins(6, 20, 6, 18)
        self.nav_buttons = {}
        for key, title in [('home','首页'),('movie','电影'),('series','电视剧'),('vr','VR电影'),('other','其他'),('discover','影片发现'),('stats','观影统计')]:
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
        self.import_control = button('＋ 添加媒体', self.import_dialog)
        self.filter_control = button('筛选', self.filter_dialog)
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
        from .home import HomePage
        self.home_page = HomePage(self)
        self.home_page.hide()
        self.toolbar = QHBoxLayout()
        self.toolbar.addWidget(button('洗牌播放全部结果', self.shuffle))
        self.toolbar.addWidget(button('保存智能片单', self.save_list))
        self.toolbar.addWidget(button('打开智能片单', self.load_list))
        self.toolbar.addWidget(button('刷新新片', self.discover))
        self.toolbar.addStretch()
        self.view_mode = QComboBox()
        self.view_mode.addItem('海报', 'poster')
        self.view_mode.addItem('缩略图', 'thumbnail')
        self.view_mode.setCurrentIndex(max(0, self.view_mode.findData(self.library.setting('view_mode', 'poster'))))
        self.view_mode.currentIndexChanged.connect(self.change_view_mode)
        self.toolbar.addWidget(self.view_mode)
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
        self.source_filter = QComboBox()
        self.source_filter.currentIndexChanged.connect(self.refresh)
        self.toolbar.addWidget(self.source_filter)
        self.category_filter = QComboBox()
        self.category_filter.addItem('全部分类', '')
        self.category_filter.currentIndexChanged.connect(self.refresh)
        self.toolbar.addWidget(self.category_filter)
        main.addLayout(self.toolbar)
        main.addWidget(self.home_page, 1)
        self.splitter = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('文件夹')
        self.tree.itemClicked.connect(self.folder_selected)
        self.splitter.addWidget(self.tree)
        self.cards = PosterList(self.play_work)
        self.cards.setObjectName('posters')
        self.cards.setViewMode(QListWidget.ViewMode.IconMode)
        self.cards.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.cards.setMovement(QListWidget.Movement.Static)
        self.cards.setSpacing(4)
        self.cards.setMouseTracking(True)
        self.cards.setUniformItemSizes(True)
        self.cards.setItemDelegate(PosterDelegate(self.cards))
        self.cards.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cards.itemClicked.connect(self.open_item)
        self.cards.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cards.customContextMenuRequested.connect(self.card_menu)
        self.cards.verticalScrollBar().valueChanged.connect(self.load_more)
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
        self.job_progress = QProgressBar()
        self.job_progress.setMaximumHeight(18)
        self.job_progress.hide()
        root.addWidget(self.job_progress)
        self.cancel_job = button('停止当前任务',self.stop_jobs)
        self.cancel_job.hide()
        root.addWidget(self.cancel_job)
        self.status = label('就绪', 'subtitle')
        self.status.setWordWrap(True)
        self.status.setContentsMargins(42, 4, 42, 8)
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

    def schedule_media(self):
        if self.jobs or self._closing:
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

    def navigate(self, section):
        self.back_details()
        self.drawer.hide()
        self.section, self.subtab = section, 0
        self.filters = {}
        self.search.clear()
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        titles = {'home':['为你推荐','继续观看','最近入库','想看'], 'movie':['影片海报墙','女演员墙'], 'series':['剧集海报墙'],
                  'vr':['VR影片海报墙'], 'other':['文件夹浏览'], 'discover':['为你发现','网站最新收录','想看清单'], 'stats':['数据概览','日趋势','周趋势','月趋势','年度报告','影片偏好','评分分布','观看历史']}
        for text in titles[section]:
            self.tabs.addTab(text)
        self.tabs.blockSignals(False)
        self.heading.setText({'home':'首页','movie':'电影','series':'电视剧','vr':'VR电影','other':'其他视频','discover':'影片发现','stats':'观影统计'}[section])
        for key, b in self.nav_buttons.items():
            b.setChecked(key == section)
        if section == 'discover':
            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem('全部来源', '')
            for p in Plugins(self.library).installed():
                self.source_filter.addItem(p['name'], p['id'])
            self.source_filter.blockSignals(False)
        self.refresh()

    def tab_changed(self, index):
        self.subtab = max(index, 0)
        self.refresh()

    def effective_filters(self):
        filters = dict(self.filters)
        if self.section in KINDS:
            filters.setdefault('kinds', [self.section])
        if self.section == 'home' and self.subtab == 3:
            filters['watchlist'] = True
        if self.section == 'home' and self.subtab == 1:
            filters['continue'] = True
        if self.section == 'movie' and self.subtab == 1:
            filters['female_cast'] = True
        if self.search.text().strip():
            filters['query'] = self.search.text().strip()
        return filters

    def change_view_mode(self):
        self.library.set_setting('view_mode', self.view_mode.currentData())
        if self.view_mode.currentData() == 'thumbnail':
            for file in self.library.db.execute('SELECT f.id,f.digest FROM files f JOIN import_cache c ON c.file_id=f.id WHERE c.pending=0').fetchall():
                if not (self.library.directory / 'cache' / (file['digest'] + '.jpg')).exists():
                    with self.library.db:
                        self.library.db.execute('UPDATE import_cache SET pending=2 WHERE file_id=?',(file['id'],))
        self.refresh()

    def card_data(self, data, landscape=False):
        record = dict(data)
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
        request={'section':self.section,'tab':self.subtab,'filters':self.effective_filters(),
                 'actor_min':self.actor_min.currentData(),'actor_sort':self.actor_sort.currentData(),
                 'year':getattr(self,'report_year',__import__('datetime').datetime.now().year)}
        if _data is None:
            self._browse_epoch+=1
            count=self.library.db.execute('SELECT COUNT(*) FROM works').fetchone()[0]
            if count>=250:
                self._browse_pending=(self._browse_epoch,request)
                self.subtitle.setText('正在后台读取媒体库…')
                if not self.jobs:self.status.setText('正在后台读取媒体库，页面仍可操作…')
                self.cards.setEnabled(False);self.home_page.setEnabled(False)
                self._start_browse_read()
                return
            self._browse_pending=None
            from .browse import load_view
            _data=load_view(self.library,request)
        self.cards.setEnabled(True);self.home_page.setEnabled(True)
        actresses = self.section == 'movie' and self.subtab == 1
        for index in range(4):
            self.toolbar.itemAt(index).widget().setVisible((self.section == 'discover') if index == 3 else self.section not in {'discover','stats'})
        self.view_mode.setVisible(not actresses and self.section != 'stats')
        self.actor_min.setVisible(actresses)
        self.actor_sort.setVisible(actresses)
        self.source_filter.setVisible(self.section == 'discover')
        self.category_filter.setVisible(self.section == 'discover')
        self.tree.setVisible(self.section == 'other')
        self.stats_scroll.setVisible(self.section == 'stats')
        self.splitter.setVisible(self.section != 'stats')
        self.home_page.hide()
        self.subtitle.show()
        if self.section == 'home' and self.subtab == 0:
            self.splitter.hide()
            self.empty.hide()
            self.subtitle.hide()
            for index in range(4):
                self.toolbar.itemAt(index).widget().hide()
            self.home_page.refresh(_data['home'],_data['recommendations'])
            self.home_page.show()
            self.current_items = _data['recommendations']
            return
        if self.section == 'stats':
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
            selected_category = self.category_filter.currentData()
            categories = sorted({category for w in items for category in w['metadata'].get('discovery_categories', [])})
            self.category_filter.blockSignals(True)
            self.category_filter.clear()
            self.category_filter.addItem('全部分类', '')
            for category in categories:
                self.category_filter.addItem(category, category)
            self.category_filter.setCurrentIndex(max(0,self.category_filter.findData(selected_category)))
            self.category_filter.blockSignals(False)
            items = [w for w in items if not self.category_filter.currentData() or self.category_filter.currentData() in w['metadata'].get('discovery_categories', [])]
            items = [w for w in items if w['sources'] and (not self.source_filter.currentData() or any(s['plugin'] == self.source_filter.currentData() for s in w['sources']))]
            if self.subtab == 2:
                items = [w for w in items if w['watchlist']]
            for w in items:
                w['_subtitle'] = ('已入库' if w['files'] else '未入库') + ' · ' + (w['sources'][0]['site_added'] or w['discovered'] or '')[:10]
        else:
            items = _data['items']
            if self.section=='other':self.build_tree(_data.get('tree'))
            if self.section == 'home' and self.subtab == 1:
                items = [w for w in items if any(f['position'] > 0 and not f['completed'] for f in w['files'])]
            elif self.section == 'home' and self.subtab == 3:
                items = [w for w in items if w['watchlist']]
        self.current_items = items
        self.cards.clear()
        self.display_count = 0
        self.append_cards()
        self.subtitle.setText(f"{len(items)} {'位女演员' if actresses else '部作品'}  ·  " + ('个人评分的算术平均 · 未评分不计入' if actresses else '点击查看详情 · 右键快速播放'))
        self.empty.setText('这里还没有内容\n\n拖入真实视频文件夹，或点击“导入文件夹”开始。\n影片发现需先在设置中安装并配置插件。' if not items else '')
        self.empty.setVisible(not items)
        self.splitter.setVisible(bool(items))

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
                if 'data' in outcome:self.refresh(_data=outcome['data'])
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

    def load_more(self, value):
        if value >= self.cards.verticalScrollBar().maximum() - 200 and self.display_count < len(self.current_items):
            self.append_cards()

    def open_item(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if 'work_ids' in data:
            self.search_metadata('actor', data['name'])
        else:
            self.open_details(data['id'])

    def open_details(self, work_id, fetch=True):
        self.back_details()
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
            self.open_details(work_id, fetch=False)
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
                self.open_details(work_id,fetch=False)
                self.details_scroll.verticalScrollBar().setValue(position)
                if result.get('errors'):self.detail_page.gallery_status.setText('部分来源未能更新：'+'；'.join(result['errors']))
        self.run_job('加载剧照与下载资源',fetch,complete)

    def back_details(self):
        if self.details_scroll is not None:
            self.pages.setCurrentWidget(self.browse_page)
            self.pages.removeWidget(self.details_scroll)
            self.details_scroll.deleteLater()
            self.details_scroll = None
            self.detail_page = None

    def search_metadata(self, field, value):
        self.navigate('home')
        self.tabs.setCurrentIndex(2)
        self.filters = {field: [value] if field == 'tags_all' else value}
        self.heading.setText(('标签：' if field == 'tags_all' else '演员：') + value)
        self.refresh()

    def card_menu(self, position):
        item = self.cards.itemAt(position)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction('查看详情', lambda: self.open_item(item))
        if data.get('kind'):menu.addAction('从本地 NFO 补充图片…',lambda:self.import_nfo_artwork(data['id']))
        if data.get('kind'):
            menu.addAction('取消喜欢' if data.get('favorite') else '喜欢', lambda: self.toggle_favorite(data['id']))
        if data.get('files'):
            menu.addAction('播放 / 继续观看', lambda: self.play_work(data['id']))
        if data.get('kind') in {'movie', 'vr'}:
            target = 'movie' if data['kind'] == 'vr' else 'vr'
            menu.addAction('移至' + KINDS[target], lambda: self.change_movie_kind(data['id'], target))
        menu.exec(self.cards.mapToGlobal(position))

    def change_movie_kind(self, work_id, kind):
        try:
            self.library.set_movie_kind(work_id, kind)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, '分类未更改', str(exc))

    def toggle_favorite(self, work_id):
        work = self.library.work(work_id)
        self.library.update_personal(work_id, favorite=not work['favorite'])
        self.refresh()

    def search_all(self):
        query = self.search.text()
        self.navigate('home')
        self.tabs.setCurrentIndex(2)
        self.search.setText(query)
        self.refresh()

    def filter_dialog(self):
        dialog = FilterDialog(self.effective_filters(), self, self.library.filter_options(local=self.section != 'discover'))
        if dialog.exec():
            filters = dialog.filters()
            if not filters['kinds']:
                QMessageBox.information(self, '筛选范围', '请至少选择一个媒体分区。')
                return
            self.navigate('home')
            self.subtab = 2
            self.tabs.setCurrentIndex(2)
            self.filters = filters
            self.search.setText(filters.get('query', ''))
            self.refresh()

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
        path = QFileDialog.getExistingDirectory(self, '导入文件夹 · 原文件保留')
        if path:
            self.import_path(path)

    def import_path(self, path):
        default = list(KINDS).index(self.section) if self.section in KINDS else 0
        title, ok = QInputDialog.getItem(self, '导入媒体', '选择媒体类型', list(KINDS.values()), default, False)
        if not ok:
            return
        kind = next(k for k,v in KINDS.items() if v == title)
        def complete(result):
            self.status.setText(f"导入 {result['imported']} · NFO 更新 {result.get('nfo_updated',0)} · 重复 {result['duplicates']} · 失败 {len(result['errors'])} · 警告 {len(result['warnings'])}")
            self.navigate(kind)
            if kind != 'other':
                self.auto_scrape_import(path, kind)
        self.run_job('快速导入 · 时长与缺失图片稍后补充', lambda lib, p: lib.import_folder(path, kind, p, fast=True, cancelled=p.cancelled), complete)

    def auto_scrape_import(self, path, kind):
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
        for job in self.jobs:
            job.requestInterruption()
        self.cancel_job.setEnabled(False)
        self.status.setText('正在安全停止任务…')

    def run_job(self, title, function, callback=None):
        if self._closing:
            return
        if any(j.isRunning() for j in self.jobs):
            QMessageBox.information(self, '任务进行中', '请等待当前后台任务完成后再执行此操作。播放和浏览仍可继续。')
            return
        self.status.setText(title + '…')
        self.job_progress.setRange(0, 0)
        self.job_progress.show()
        self.cancel_job.setEnabled(True)
        self.cancel_job.setVisible(title.startswith(('直接下载','快速导入','后台补充','本地 NFO','检查下载')))
        job = Job(self.library.directory, function, self)
        self.jobs.append(job)
        last_refresh = [time.monotonic()]
        def show_progress(done, total, message):
            if total>2147483647:
                self.job_progress.setRange(0,10000)
                self.job_progress.setValue(min(10000,int(done*10000//total)))
                self.job_progress.setFormat('%p%')
            else:
                self.job_progress.setRange(0,total)
                self.job_progress.setValue(done if total else 0)
                self.job_progress.setFormat('%v / %m · %p%')
            self.status.setText(title + ' · ' + message)
            if title.startswith('快速导入') and self.detail_page is None and time.monotonic() - last_refresh[0] > 2:
                self.refresh()
                last_refresh[0] = time.monotonic()
        job.progress.connect(show_progress)
        # Deliver completion after the thread exits, allowing dependent jobs to start.
        outcome = {}
        job.done.connect(lambda value: outcome.update(value=value))
        job.failed.connect(lambda error: outcome.update(error=error))
        def finished():
            self.job_progress.hide()
            self.cancel_job.hide()
            self.jobs.remove(job)
            job.deleteLater()
            if self._closing:
                if not self.jobs and self._browse_job is None:
                    QTimer.singleShot(0, self.close)
                return
            from .images import image_cache
            image_cache().invalidate()
            self.refresh()
            if 'error' in outcome:
                self.status.setText(title + '失败：' + outcome['error'])
                QMessageBox.warning(self, title, outcome['error'])
            elif isinstance(outcome.get('value'), dict) and outcome['value'].get('cancelled'):
                self.status.setText('任务已停止，已完成内容保留')
            else:
                self.status.setText(title + '完成')
                if callback:
                    callback(outcome.get('value'))
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
        dialog = QDialog(self)
        dialog.setWindowTitle('随机播放 · 等概率洗牌')
        dialog.resize(620, 600)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('每部电影 / 整部剧 / 其他视频为一个对象', 'subtitle'))
        queue = self.library.setting('queue', {'ids':[], 'index':0})
        items = QListWidget()
        for i, work_id in enumerate(queue['ids']):
            try:
                w = self.library.work(work_id)
                items.addItem(f"{'▶' if i == queue['index'] else '  '} {i+1}. {w['title']} · {KINDS[w['kind']]}")
            except ValueError:
                items.addItem(f'{i+1}. 已移除的作品')
        items.setCurrentRow(queue['index'])
        layout.addWidget(items)
        def update_position():
            current_queue = self.library.setting('queue', {'ids':[], 'index':0})
            if current_queue['ids'] != queue['ids']:
                return
            for row, work_id in enumerate(queue['ids']):
                item = items.item(row)
                if item:
                    text = item.text()
                    item.setText(('▶ ' if row == current_queue['index'] else '  ') + text[2:])
            items.setCurrentRow(current_queue['index'] if current_queue['index'] < items.count() else -1)
        timer = QTimer(dialog)
        timer.setInterval(500)
        timer.timeout.connect(update_position)
        timer.start()
        row = QHBoxLayout()
        row.addWidget(button('上一作品', lambda: self.queue_play(-1)))
        row.addWidget(button('继续队列', lambda: self.queue_play(0), True))
        row.addWidget(button('下一作品', lambda: self.queue_play(1)))
        layout.addLayout(row)
        def configure():
            f = FilterDialog(queue.get('filters', {}), dialog, self.library.filter_options())
            if f.exec():
                if not f.filters()['kinds']:
                    return
                self.shuffle(f.filters())
                dialog.accept()
        layout.addWidget(button('设置全局范围 / 重新洗牌', configure))
        dialog.exec()

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
        if self._closing:
            return
        if any(j.isRunning() for j in self.jobs):
            return
        due = [p['id'] for p in Plugins(self.library).installed() if p['config'].get('enabled') and 'discover' in p['capabilities'] and p['config'].get('auto_refresh', False)
               and time.time() - max(p['config'].get('last_refresh', 0), p['config'].get('last_attempt', 0)) > max(1, p['config'].get('interval_hours', 24)) * 3600]
        if due:
            self.run_job('定期发现新片', lambda lib, p: self.refresh_plugins(lib, due))

    def show_tasks(self):
        dialog = QDialog(self)
        dialog.resize(950, 650)
        dialog.setWindowTitle('任务与诊断')
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(['类型','状态','更新时间','详情 / 失败原因'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        rows = [dict(r) for r in self.library.db.execute('SELECT * FROM tasks ORDER BY updated DESC LIMIT 300')]
        for row, task in enumerate(rows):
            table.insertRow(row)
            for column, text in enumerate([task['kind'], task['status'], task['updated'][:19], task['error'] or task['result']]):
                item = QTableWidgetItem(str(text))
                item.setToolTip(str(text))
                table.setItem(row, column, item)
        layout.addWidget(table)
        def inspect_task():
            index = table.currentRow()
            if index >= 0:
                task = rows[index]
                detail = QDialog(dialog)
                detail.setWindowTitle('任务完整详情')
                detail.resize(850, 600)
                content = QVBoxLayout(detail)
                text = QPlainTextEdit(json.dumps({**task, 'payload':json.loads(task['payload']), 'result':json.loads(task['result'])}, ensure_ascii=False, indent=2))
                text.setReadOnly(True)
                content.addWidget(text)
                content.addWidget(button('关闭', detail.accept))
                detail.exec()
        layout.addWidget(button('查看完整进度 / 结果 / 错误', inspect_task))
        def retry():
            index = table.currentRow()
            if index < 0:
                return
            task = rows[index]
            payload = json.loads(task['payload'])
            if task['kind'] == 'move':
                dialog.accept()
                self.run_job('恢复文件整理', lambda lib, p: execute_move(lib, task_id=task['id']))
            elif task['kind'] == 'import':
                dialog.accept()
                self.run_job('重试导入', lambda lib, p: lib.import_folder(payload['root'], payload['kind'], p, fast=payload.get('fast',True), cancelled=p.cancelled))
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
        dialog.exec()

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
                server = LanServer(self.library.directory,port=port)
                server.start()
                self.lan_server = server
            self.library.set_setting('lan', {'enabled':enabled,'port':port})
        except Exception:
            if previous:
                previous.start()
                self.lan_server = previous
            raise

    def settings(self):
        from .settings import Settings
        Settings(self).exec()
        self.refresh()
        if self.detail_page is not None:self.reload_details(self.detail_page.work_id)

    def closeEvent(self, event):
        self._closing = True
        if self.jobs or self._browse_job is not None:
            self._closing = True
            self._browse_pending=None
            if self._browse_job is not None:self._browse_job.requestInterruption()
            self.scheduler.stop()
            self.media_scheduler.stop()
            self.status.setText('正在停止任务并保存已完成记录…')
            for job in self.jobs:
                job.requestInterruption()
            event.ignore()
            return
        self.player.close()
        self.scheduler.stop()
        self.media_scheduler.stop()
        if self.lan_server:
            self.lan_server.stop()
        self.library.close()
        event.accept()
