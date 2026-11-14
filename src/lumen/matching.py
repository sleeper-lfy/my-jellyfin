"""Visual, single-selection matching for the current detail page."""
import hashlib
import copy
import threading
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, QSize, Qt, QTimer, QByteArray, QBuffer, QIODevice, QSaveFile
from PySide6.QtGui import QIcon, QPixmap, QImageReader
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox, QAbstractItemView, QCheckBox, QPushButton, QPlainTextEdit
from .core import Library
from .plugins import Plugins


def preview_cover(library, plugin_id, record):
    """Cache only a bounded preview through the plugin's declared network policy."""
    url = record.get('poster') or record.get('photo')
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
    output = QSaveFile(str(path))
    if picture.isNull() or not output.open(QIODevice.OpenModeFlag.WriteOnly) or not picture.save(output, 'JPG') or not output.commit():
        raise ValueError('候选封面解码失败')
    return str(path)


def match_conflict(library, plugin, candidate, work_id):
    from .plugins import external_ids_conflict
    from .core import identity
    work = library.work(work_id)
    incoming = {str(key).lower():str(value) for key,value in candidate.get('external_ids',{}).items() if value is not None and str(value)}
    stored = list(library.db.execute('SELECT namespace,value FROM external_ids WHERE work_id=?',(work_id,)))
    linked = set()
    for namespace,value in incoming.items():
        row = library.db.execute('SELECT work_id FROM external_ids WHERE kind=? AND namespace=? AND value=?',(work['kind'],namespace,value)).fetchone()
        if row and row[0]!=work_id:linked.add(row[0])
    row = library.db.execute('SELECT work_id FROM sources WHERE plugin=? AND source_id=?',(plugin['id'],str(candidate['id']))).fetchone()
    if row and row[0]!=work_id:linked.add(row[0])
    key = identity(candidate['title'],candidate.get('year'),work['kind'])
    for row in library.db.execute('SELECT work_id FROM name_keys WHERE key=? UNION SELECT id FROM works WHERE identity=?',(key,key)):
        if row[0]!=work_id:linked.add(row[0])
    if not linked and not external_ids_conflict(stored,incoming):return None
    related = [library.work(identifier) for identifier in sorted(linked)]
    return {'current_title':work['title'], 'stored':dict(stored), 'incoming':incoming,
            'related':[{'id':item['id'],'title':item['title'],'kind':item['kind'],'files':len(item['files']),
                        'path':item['files'][0]['path'] if item['files'] else ''} for item in related],
            'can_merge':bool(related) and all(item['kind']==work['kind'] for item in related)}


def apply_match(library, plugin, operation, candidate, work_id, *, cancelled=None, force=False,
                interactive=False, resolution=None, snapshot=None, media_library_id=None):
    if media_library_id is not None:library.work(work_id,media_library_id)
    manager = Plugins(library)
    from .metadata_health import overwrite_snapshot, overwrite_metadata
    if snapshot is not None and overwrite_snapshot(library, work_id)!=snapshot:
        raise ValueError('选择期间影片资料已修改，请重新刮削后再确认')
    snapshot = snapshot if snapshot is not None else overwrite_snapshot(library, work_id)
    if operation == 'search' and 'detail' in plugin['capabilities']:
        records = manager.run(plugin['id'], 'detail', url=candidate['url'],
                              **({'cancelled': cancelled} if cancelled else {}), **({'refresh': True} if force else {}))
        exact = [record for record in records if str(record['id']) == str(candidate['id'])]
        if len(exact) != 1:
            raise ValueError('详情来源标识与所选候选不匹配，未更新资料')
        candidate = exact[0]
    if resolution == 'keep':
        candidate = copy.deepcopy(candidate)
        current = dict(library.db.execute('SELECT namespace,value FROM external_ids WHERE work_id=?',(work_id,)))
        current.update(snapshot[0]['metadata'].get('external_ids',{}))
        candidate['external_ids'] = {**candidate.get('external_ids',{}),**current}
    conflict = match_conflict(library, plugin, candidate, work_id)
    if conflict and (interactive or not force) and resolution != 'replace':
        if interactive:
            return {'conflict':conflict,'candidate':candidate,'snapshot':snapshot,'work_id':work_id}
        raise ValueError('影片编号或来源存在冲突，请在单片刮削中选择保留编号、覆盖或合并')
    if conflict and conflict['related']:
        raise ValueError('所选编号或来源已关联其他影片，请先核对或使用合并预览')
    force = force or resolution == 'replace'
    # Explicit selection updates unlocked NFO fields; background refresh still preserves them.
    if force:
        result = overwrite_metadata(library, plugin, candidate, work_id, cancelled=cancelled, snapshot=snapshot)
        result['work_id'] = work_id
    else:
        result = manager.merge(plugin['id'], candidate, work_id, replace_nfo=True, cancelled=cancelled)
    from .ingestion import confirm
    confirm(library, work_id, media_library_id)
    return result


class MatchConflictDialog(QDialog):
    def __init__(self, conflict, parent=None):
        super().__init__(parent);self.setWindowTitle('选择如何处理刮削冲突');self.resize(620,440)
        self.choice=None
        layout=QVBoxLayout(self)
        note=QLabel('所选资料与当前影片的编号或来源不一致。请选择处理方式，确认前不会修改媒体库。')
        note.setWordWrap(True);layout.addWidget(note)
        lines=['当前影片：'+conflict['current_title'],'','原编号：']
        lines += [key+'：'+value for key,value in conflict['stored'].items()] or ['无']
        lines += ['','所选资料的编号：']
        lines += [key+'：'+value for key,value in conflict['incoming'].items()] or ['无']
        for work in conflict['related']:
            lines += ['','关联影片：'+work['title'],f"文件数：{work['files']}",work['path']]
        report=QPlainTextEdit('\n'.join(lines));report.setReadOnly(True);layout.addWidget(report,1)
        def action(text,choice):
            button=QPushButton(text);button.setObjectName('matchConflict:'+choice)
            button.clicked.connect(lambda:self.choose(choice));layout.addWidget(button)
        if not conflict['related']:
            action('保留原编号，更新其他资料','keep')
            action('采用所选编号，强制覆盖当前影片资料及图片','replace')
        else:
            action('查看关联影片','view')
            if conflict['can_merge']:action('预览合并关联影片（保留文件和观看记录）','merge')
        cancel=QPushButton('取消本次刮削');cancel.clicked.connect(self.reject);layout.addWidget(cancel)

    def choose(self,choice):
        self.choice=choice;self.accept()


class PreviewLoader(QObject):
    loaded = Signal(int, str)
    def __init__(self):
        super().__init__();self.cancelled=threading.Event()


class PreviewTask(QRunnable):
    def __init__(self, loader, directory, plugin_id, index, record):
        super().__init__()
        self.loader, self.directory, self.plugin_id, self.index, self.record = loader, directory, plugin_id, index, record

    def run(self):
        library = None
        try:
            library = Library(self.directory, initialize=False)
            library.cancelled=self.loader.cancelled.is_set
            path = preview_cover(library, self.plugin_id, self.record)
            self.loader.loaded.emit(self.index, path or '')
        except Exception:
            self.loader.loaded.emit(self.index, '')
        finally:
            if library: library.close()


class CandidatePicker(QDialog):
    def __init__(self, directory, plugin_id, records, parent=None, *, allow_force=False):
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
        note = QLabel('点击正确影片的封面或标题即可更新当前详情；已锁定的字段会保留。')
        note.setWordWrap(True);layout.addWidget(note)
        self.force = None
        if allow_force:
            self.force = QCheckBox('强制覆盖资料及图片（包括已锁定、NFO 和自选图片）')
            self.force.setObjectName('forceScrapeOverwrite')
            layout.addWidget(self.force)
            self.force.toggled.connect(lambda checked: note.setText(
                '强制替换标题、年份、简介、标签、演员及图片；来源未提供的展示字段也会清空。保留个人评分、喜欢／收藏及播放记录。' if checked else
                '更新未锁定资料，保留自选图片。需要重新替换全部展示资料时，勾选强制覆盖。'))
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
            item.setToolTip(self.record_tooltip(record) + ('\n封面正在载入' if record.get('poster') else '\n来源未提供封面'))
            self.items.addItem(item)
        layout.addWidget(self.items)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.confirm = controls.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm.setText('使用选中结果')
        self.confirm.setEnabled(False)
        self.items.currentRowChanged.connect(lambda index: self.confirm.setEnabled(index >= 0))
        self.items.itemClicked.connect(lambda _: self.accept())
        self.items.itemActivated.connect(lambda _: self.accept())
        controls.accepted.connect(self.accept); controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        self.items.verticalScrollBar().valueChanged.connect(self.load_visible)

    def done(self,result):
        self.loader.cancelled.set()
        super().done(result)

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
        item.setToolTip(self.record_tooltip(self.records[index]) + ('' if path else '\n图片暂不可用，仍可选择此结果'))

    @staticmethod
    def record_tooltip(record):
        credit=[str(record[field]) for field in ('photo_attribution','photo_license','photo_page') if record.get(field)]
        return record['title']+'\n'+record['url']+('\n头像署名 / 许可：\n'+'\n'.join(credit) if credit else '')

    def selection(self):
        index = self.items.currentRow()
        return self.records[index] if index >= 0 else None

    def force_overwrite(self):
        return self.force is not None and self.force.isChecked()
