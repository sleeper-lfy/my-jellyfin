"""Optional engine settings; downloads and queries use the existing task queue."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
                              QLabel, QPushButton, QCheckBox, QLineEdit,
                              QSpinBox, QListWidget, QListWidgetItem, QMessageBox)

from . import javinizer


class JavinizerPanel(QWidget):
    def __init__(self, window, parent=None, changed=None):
        super().__init__(parent)
        self.window = window
        self.changed = changed
        self.setObjectName('javinizerSettings')
        config = javinizer.settings(window.library)
        layout = QVBoxLayout(self)
        note = QLabel('按番号查询影片资料，兼容电影和 VR 电影。仅在刮削时启动，完成后退出；来源失败时按顺序切换。')
        note.setWordWrap(True)
        layout.addWidget(note)
        link = QLabel(f'<a style="color:#00a4dc" href="https://github.com/javinizer/javinizer-go/releases/tag/v{javinizer.VERSION}">Javinizer-Go {javinizer.VERSION} · Windows x64 · 57 MiB · 官方发布</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setObjectName('javinizerStatus')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.download = QPushButton('下载组件并启用')
        self.download.setObjectName('downloadJavinizer')
        self.download.clicked.connect(self.download_engine)
        buttons.addWidget(self.download)
        local = QPushButton('选择已下载的官方组件…')
        local.clicked.connect(self.import_engine)
        buttons.addWidget(local)
        layout.addLayout(buttons)
        form = QFormLayout()
        layout.addLayout(form)
        self.enabled = QCheckBox('启用按需刮削引擎')
        self.enabled.setChecked(config['enabled'])
        form.addRow('状态', self.enabled)
        self.sources = QListWidget()
        self.sources.setObjectName('javinizerSources')
        self.sources.setMaximumHeight(160)
        ordered = config['sources'] + [source for source in javinizer.SOURCES if source not in config['sources']]
        for source in ordered:
            if source not in javinizer.SOURCES:
                continue
            name, hosts = javinizer.SOURCES[source]
            item = QListWidgetItem(name + ' · ' + hosts[0])
            item.setData(Qt.ItemDataRole.UserRole, source)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if source in config['sources'] else Qt.CheckState.Unchecked)
            self.sources.addItem(item)
        form.addRow('来源顺序', self.sources)
        ordering = QHBoxLayout()
        up = QPushButton('上移')
        down = QPushButton('下移')
        up.clicked.connect(lambda: self.move_source(-1))
        down.clicked.connect(lambda: self.move_source(1))
        ordering.addWidget(up)
        ordering.addWidget(down)
        ordering.addStretch()
        form.addRow('', ordering)
        self.proxy = QLineEdit(config['proxy'])
        self.proxy.setPlaceholderText('inherit 跟随默认代理；留空直连；或填写 HTTP / SOCKS5 地址')
        form.addRow('独立代理', self.proxy)
        self.timeout = QSpinBox()
        self.timeout.setRange(15, 180)
        self.timeout.setValue(config['timeout'])
        self.timeout.setSuffix(' 秒 / 来源')
        form.addRow('查询超时', self.timeout)
        self.cache_hours = QSpinBox()
        self.cache_hours.setRange(0, 720)
        self.cache_hours.setValue(config['cache_hours'])
        self.cache_hours.setSuffix(' 小时（0 为不缓存）')
        form.addRow('资料缓存有效期', self.cache_hours)
        save = QPushButton('保存引擎设置')
        save.setObjectName('saveJavinizerSettings')
        save.clicked.connect(self.save)
        form.addRow(save)
        self.query = QLineEdit()
        self.query.setPlaceholderText('例如 IPX-535；也可以粘贴包含番号的文件名')
        self.query.setObjectName('javinizerTestQuery')
        form.addRow('测试番号', self.query)
        testing = QHBoxLayout()
        test = QPushButton('测试刮削')
        test.setObjectName('testJavinizer')
        test.clicked.connect(self.test_query)
        testing.addWidget(test)
        clear = QPushButton('清除资料缓存 / 解除来源冷却')
        clear.clicked.connect(self.clear_cache)
        testing.addWidget(clear)
        form.addRow(testing)
        hint = QLabel('首次获取成功后复用本地资料缓存（最多 8 MiB / 256 条）。同一时间只运行一个查询进程；401 / 403 / 429 来源冷却 5 分钟后重试。图片由 Lumen 单独下载，失败记录在任务页。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.refresh_status()

    def refresh_status(self):
        ready = javinizer.executable_path(self.window.library).is_file()
        self.status.setText('组件已安装，运行前自动校验；空闲时不启动进程。' if ready else '尚未安装组件。下载和校验在后台任务中完成，也可选择事先下载的同版本官方 EXE。')

    def move_source(self, offset):
        row = self.sources.currentRow()
        target = row + offset
        if row < 0 or not 0 <= target < self.sources.count():
            return
        item = self.sources.takeItem(row)
        self.sources.insertItem(target, item)
        self.sources.setCurrentRow(target)

    def values(self):
        return {'enabled': self.enabled.isChecked(), 'proxy': self.proxy.text().strip(),
                'timeout': self.timeout.value(), 'cache_hours': self.cache_hours.value(),
                'sources': [self.sources.item(i).data(Qt.ItemDataRole.UserRole)
                            for i in range(self.sources.count())
                            if self.sources.item(i).checkState() == Qt.CheckState.Checked]}

    def save(self, _checked=False, *, inform=True):
        try:
            values = self.values()
            if values['enabled'] and not javinizer.executable_path(self.window.library).is_file():
                raise ValueError('请先下载组件或选择已下载的官方组件')
            javinizer.save_settings(self.window.library, values)
            if self.changed:
                self.changed()
            if inform:
                self.status.setText('设置已保存，可在影片详情或导入时选择 Javinizer-Go。')
            return True
        except ValueError as error:
            QMessageBox.warning(self, '引擎设置未保存', str(error))
            return False

    def start_install(self, local_file=None):
        # Persist proxy/source edits before a background download, without enabling a missing binary.
        try:
            previous = javinizer.settings(self.window.library)['enabled']
            javinizer.save_settings(self.window.library, {**self.values(), 'enabled': previous})
        except ValueError as error:
            QMessageBox.warning(self, '无法安装组件', str(error))
            return
        self.status.setText('组件已加入后台任务；可在主窗口查看进度或停止任务。')
        def complete(_result):
            try:
                self.enabled.setChecked(True)
                self.refresh_status()
                if self.changed:
                    self.changed()
            except RuntimeError:
                pass  # The settings dialog may have closed while the task ran.
        self.window.run_job('安装 Javinizer-Go 组件',
                            lambda lib, p: javinizer.install(lib, p, p.cancelled, local_file=local_file), complete)

    def download_engine(self):
        self.start_install()

    def import_engine(self):
        from .dialogs import open_file_name
        path = open_file_name(self, '选择 Javinizer-Go 官方 Windows x64 EXE', '', '可执行文件 (*.exe)')
        if path:
            self.start_install(path)

    def test_query(self):
        try:
            code = javinizer.movie_code(self.query.text())
        except ValueError as error:
            QMessageBox.information(self, '请输入番号', str(error))
            return
        if not self.save(inform=False):
            return
        from .plugins import Plugins
        self.status.setText('测试已加入后台任务；测试只查询资料。')
        def complete(records):
            try:
                self.status.setText(('命中：' + records[0]['title'] + ' · ' + records[0]['javinizer_source']) if records else '所有来源均未收录此番号。')
            except RuntimeError:
                pass
        self.window.run_job('测试番号刮削', lambda lib, p: Plugins(lib).run(
            javinizer.ENGINE_ID, 'search', query=code, cancelled=p.cancelled, progress=p), complete)

    def clear_cache(self):
        def complete(result):
            try:
                self.status.setText(f"已清除 {result['removed']} 条资料缓存与来源冷却记录；影片资料和图片保留。")
            except RuntimeError:
                pass
        self.window.run_job('清除刮削查询缓存', lambda lib, p: javinizer.clear_cache(lib), complete)
