"""Visual, single-selection matching for the current detail page."""
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, QSize, Qt, QTimer, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QIcon, QPixmap, QImageReader
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox, QAbstractItemView
from .core import Library
from .plugins import Plugins


def preview_cover(library, plugin_id, record):
    """Cache only a bounded preview through the plugin's declared network policy."""
    url = record.get('poster')
    if not url:
        return None
    manager = Plugins(library)
    plugin = next(p for p in manager.installed() if p['id'] == plugin_id)
    parsed = urlparse(url)
    if not plugin['config'].get('enabled') or parsed.scheme not in {'http', 'https'} or parsed.hostname not in plugin['domains'] or parsed.username or parsed.password:
        raise ValueError('封面不在插件声明的网络权限内')
    path = library.directory / 'cache' / ('match-' + hashlib.sha256((plugin_id + url).encode()).hexdigest() + '.jpg')
    if path.is_file():
        return str(path)
    data, content_type = manager.fetch(plugin, url, image=True)
    if not content_type.startswith('image/'):
        raise ValueError('候选封面响应不是图片')
    buffer = QBuffer(); buffer.setData(QByteArray(data)); buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer); reader.setAutoTransform(True); size = reader.size()
    if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > 40_000_000:
        raise ValueError('候选封面无效或过大')
    reader.setScaledSize(size.scaled(QSize(300, 450), Qt.AspectRatioMode.KeepAspectRatio))
    picture = reader.read()
    if picture.isNull() or not picture.save(str(path), 'JPG'):
        raise ValueError('候选封面解码失败')
    return str(path)


def apply_match(library, plugin, operation, candidate, work_id):
    manager = Plugins(library)
    if operation == 'search' and 'detail' in plugin['capabilities']:
        records = manager.run(plugin['id'], 'detail', url=candidate['url'])
        exact = [record for record in records if str(record['id']) == str(candidate['id'])]
        if len(exact) != 1:
            raise ValueError('详情来源标识与所选候选不匹配，未更新资料')
        candidate = exact[0]
    # Explicit selection updates unlocked NFO fields; background refresh still preserves them.
    return manager.merge(plugin['id'], candidate, work_id, replace_nfo=True)


class PreviewLoader(QObject):
    loaded = Signal(int, str)


class PreviewTask(QRunnable):
    def __init__(self, loader, directory, plugin_id, index, record):
        super().__init__()
        self.loader, self.directory, self.plugin_id, self.index, self.record = loader, directory, plugin_id, index, record

    def run(self):
        library = None
        try:
            library = Library(self.directory, initialize=False)
            path = preview_cover(library, self.plugin_id, self.record)
            self.loader.loaded.emit(self.index, path or '')
        except Exception:
            self.loader.loaded.emit(self.index, '')
        finally:
            if library: library.close()


class CandidatePicker(QDialog):
    def __init__(self, directory, plugin_id, records, parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择刮削结果 · 选定后更新当前详情')
        self.resize(840, 620)
        self.records = records
        self.directory, self.plugin_id = directory, plugin_id
        self.requested = set()
        self.loader = PreviewLoader()
        self.loader.loaded.connect(self.loaded)
        app = QApplication.instance()
        if not hasattr(app, 'matching_pool'):
            app.matching_pool = QThreadPool(app)
            app.matching_pool.setMaxThreadCount(3)
        self.pool = app.matching_pool
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('点击正确影片的封面或标题即可更新当前详情；已锁定的字段会保留。'))
        self.items = QListWidget()
        self.items.setViewMode(QListWidget.ViewMode.IconMode)
        self.items.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.items.setMovement(QListWidget.Movement.Static)
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items.setIconSize(QSize(140, 190))
        self.items.setGridSize(QSize(190, 310))
        self.items.setWordWrap(True)
        self.items.setTextElideMode(Qt.TextElideMode.ElideNone)
        placeholder = QPixmap(140, 190); placeholder.fill(Qt.GlobalColor.darkGray)
        for record in records:
            item = QListWidgetItem(QIcon(placeholder), record['title'] + '\n' + str(record.get('year') or '未知年份'))
            item.setSizeHint(QSize(180, 300))
            item.setToolTip(record['title'] + '\n' + record['url'] + ('\n封面正在载入' if record.get('poster') else '\n来源未提供封面'))
            self.items.addItem(item)
        layout.addWidget(self.items)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.confirm = controls.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm.setText('使用选中结果')
        self.confirm.setEnabled(False)
        self.items.currentRowChanged.connect(lambda index: self.confirm.setEnabled(index >= 0))
        self.items.itemClicked.connect(lambda _: self.accept())
        self.items.itemActivated.connect(lambda _: self.accept())
        controls.accepted.connect(self.accept); controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        self.items.verticalScrollBar().valueChanged.connect(self.load_visible)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.load_visible)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.load_visible)

    def load_visible(self, *_):
        if not self.isVisible(): return
        rect = self.items.viewport().rect()
        for index, record in enumerate(self.records):
            if index in self.requested or not self.items.visualItemRect(self.items.item(index)).intersects(rect): continue
            self.requested.add(index)
            if record.get('poster'):
                self.pool.start(PreviewTask(self.loader, self.directory, self.plugin_id, index, record))

    def loaded(self, index, path):
        item = self.items.item(index)
        if path: item.setIcon(QIcon(path))
        item.setToolTip(self.records[index]['title'] + '\n' + self.records[index]['url'] + ('' if path else '\n封面暂不可用，仍可选择此影片'))

    def selection(self):
        index = self.items.currentRow()
        return self.records[index] if index >= 0 else None
