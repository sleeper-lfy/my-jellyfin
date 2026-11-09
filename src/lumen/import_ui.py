"""A reusable nonblocking import form; directory access belongs to the worker."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QLineEdit,QComboBox,QPushButton,QLabel,QDialogButtonBox,QFileDialog

SCRAPABLE={'movie','series','vr'}


class ImportDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.browser=None;self.pending=[]
        self.setAcceptDrops(True)
        self.setWindowTitle('添加媒体');self.resize(640,300)
        layout=QVBoxLayout(self);note=QLabel('拖入或粘贴视频文件 / 文件夹路径。单个文件只导入该文件，原文件保留；重复导入会跳过未变化文件并更新 NFO。');note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();layout.addLayout(form);row=QHBoxLayout()
        self.path=QLineEdit();self.path.setPlaceholderText('例如 D:\\Video；也可直接粘贴目录路径');self.path.setMinimumWidth(0);row.addWidget(self.path,1)
        browse=QPushButton('选择目录…');browse.clicked.connect(self.choose);row.addWidget(browse);form.addRow('媒体目录',row)
        self.kind=QComboBox()
        from .ui import KINDS
        for key,title in KINDS.items():self.kind.addItem(title,key)
        form.addRow('媒体类型',self.kind)
        self.scraper=QComboBox();form.addRow('导入后刮削',self.scraper)
        self.destination=QLineEdit();self.destination.setPlaceholderText('留空表示导入后不移动文件')
        destination_row=QHBoxLayout();destination_row.addWidget(self.destination,1)
        destination_browse=QPushButton('选择目录…');destination_browse.clicked.connect(self.choose_destination);destination_row.addWidget(destination_browse)
        form.addRow('整理目标',destination_row)
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.kind.currentIndexChanged.connect(lambda:self.sync_kind())
        self.scraper.currentIndexChanged.connect(lambda:self.message.setText(self.hint()))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('开始导入 / 加入队列')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.submit);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.refresh_scrapers()
    def refresh_scrapers(self):
        from .plugins import Plugins
        selected=self.scraper.currentData()
        self.scraper.clear();self.scraper.addItem('不刮削','')
        for plugin in Plugins(self.window.library).installed():
            if plugin['config'].get('enabled') and 'search' in plugin['capabilities'] and (not plugin.get('media_kinds') or self.kind.currentData() in plugin['media_kinds']):
                self.scraper.addItem(plugin['name'],plugin['id'])
        self.scraper.setCurrentIndex(max(0,self.scraper.findData(selected) if selected else 0))
    def sync_kind(self):
        self.refresh_scrapers()
        kind=self.kind.currentData()
        scrapable=kind in SCRAPABLE
        self.scraper.setEnabled(scrapable);self.destination.setEnabled(scrapable)
        config=self.window.library.setting('partition:'+kind,{}) if scrapable else {}
        index=self.scraper.findData(config.get('plugin') or '')
        if index>0:self.scraper.setCurrentIndex(index)
        else:
            self.scraper.blockSignals(True);self.scraper.setCurrentIndex(0);self.scraper.blockSignals(False)
        self.destination.setText(config.get('destination','') or '')
        self.message.setText(self.hint())
    def hint(self):
        kind=self.kind.currentData()
        if kind=='fans':text='Fans 按总目录的第一层作者文件夹归组，包含作者下级目录的视频；不要求季集编号、不自动影视刮削。'
        elif kind in SCRAPABLE:text='导入后按所选插件刮削，编号或标题、年份、类型唯一匹配后自动补全资料；歧义在任务页待确认；整理目标留空则不移动文件。'
        else:text='此类型按原文件名入库，不自动刮削。'
        if kind in SCRAPABLE and not self.scraper.currentData():text+='当前未选择刮削来源，导入后只入库；要自动刮削，请先选择来源。'
        text+='已有后台任务时会排队处理，仍可继续添加其他目录。'
        if self.pending:text+=f'本次拖入共 {len(self.pending)+1} 个文件或文件夹，确认后其余将按相同设置依次加入队列。'
        return text
    def add_folders(self,paths):
        current=self.path.text().strip()
        for path in paths:
            if not current:self.path.setText(path);current=path
            elif path!=current and path not in self.pending:self.pending.append(path)
        self.message.setText(self.hint())
    def dragEnterEvent(self,event):self.window.dragEnterEvent(event)
    def dragMoveEvent(self,event):self.window.dragMoveEvent(event)
    def dropEvent(self,event):self.window.dropEvent(event)
    def choose_destination(self):
        from .dialogs import existing_directory
        path=existing_directory(self,'选择整理目标目录',self.destination.text())
        if path:self.destination.setText(path)
    def choose(self):
        if self.browser is not None and self.browser.isVisible():self.browser.raise_();self.browser.activateWindow();return
        from .dialogs import _picker
        browser=_picker(self,'选择媒体目录',self.path.text().strip().strip('"'))
        browser.setOption(QFileDialog.Option.DontResolveSymlinks,True);browser.setFileMode(QFileDialog.FileMode.Directory);browser.setOption(QFileDialog.Option.ShowDirsOnly,True)
        browser.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);self.browser=browser
        browser.fileSelected.connect(self.path.setText)
        browser.finished.connect(lambda _:setattr(self,'browser',None));browser.open()
    def submit(self):
        path=self.path.text().strip().strip('"')
        if not path:self.message.setText('请先填写或选择媒体目录。');self.path.setFocus();return
        kind=self.kind.currentData()
        plugin=(self.scraper.currentData() or '') if kind in SCRAPABLE else ''
        destination=self.destination.text().strip() if kind in SCRAPABLE else ''
        batch=self.pending;self.pending=[]
        self.accept();self.window.start_import(path,kind,plugin,destination,batch)
    def done(self,result):
        if self.browser is not None:self.browser.reject()
        super().done(result)
