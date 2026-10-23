"""A reusable nonblocking import form; directory access belongs to the worker."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QLineEdit,QComboBox,QPushButton,QLabel,QDialogButtonBox,QFileDialog


class ImportDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.browser=None
        self.setWindowTitle('添加媒体');self.resize(640,240)
        layout=QVBoxLayout(self);note=QLabel('选择或粘贴资源目录。原文件保留；重复导入会跳过未变化文件并更新 NFO。');note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();layout.addLayout(form);row=QHBoxLayout()
        self.path=QLineEdit();self.path.setPlaceholderText('例如 D:\\Video；也可直接粘贴目录路径');self.path.setMinimumWidth(0);row.addWidget(self.path,1)
        browse=QPushButton('选择目录…');browse.clicked.connect(self.choose);row.addWidget(browse);form.addRow('媒体目录',row)
        self.kind=QComboBox()
        from .ui import KINDS
        for key,title in KINDS.items():self.kind.addItem(title,key)
        form.addRow('媒体类型',self.kind)
        self.message=QLabel('已有后台任务时会排队处理，仍可继续添加其他目录。');self.message.setWordWrap(True);layout.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('开始导入 / 加入队列')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.submit);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def choose(self):
        if self.browser is not None and self.browser.isVisible():self.browser.raise_();self.browser.activateWindow();return
        # Native shell extensions and nested modal loops can stall on unavailable drives.
        browser=QFileDialog(self,'选择媒体目录');browser.setOption(QFileDialog.Option.DontUseNativeDialog,True)
        browser.setOption(QFileDialog.Option.DontResolveSymlinks,True);browser.setFileMode(QFileDialog.FileMode.Directory);browser.setOption(QFileDialog.Option.ShowDirsOnly,True)
        browser.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);self.browser=browser
        browser.fileSelected.connect(self.path.setText)
        browser.finished.connect(lambda _:setattr(self,'browser',None));browser.open()
    def submit(self):
        path=self.path.text().strip().strip('"')
        if not path:self.message.setText('请先填写或选择媒体目录。');self.path.setFocus();return
        kind=self.kind.currentData();self.accept();self.window.start_import(path,kind)
    def done(self,result):
        if self.browser is not None:self.browser.reject()
        super().done(result)
