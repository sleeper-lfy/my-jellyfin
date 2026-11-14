"""Windows startup/background controls, separate from metadata and data safety."""
import sqlite3
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QCheckBox,QLabel,QMessageBox
from . import startup


def note(text):
    widget=QLabel(text);widget.setWordWrap(True);return widget


class StartupSettings(QWidget):
    def __init__(self,window):
        super().__init__();self.library=window.library
        outer=QVBoxLayout(self);outer.setContentsMargins(16,16,16,16);outer.setSpacing(12)
        title=note('启动与后台');title.setObjectName('panelTitle');outer.addWidget(title)
        outer.addWidget(note('设置登录 Windows 后自动启动，以及首次启动时是否显示主窗口。'))
        form=QFormLayout();form.setSpacing(12);outer.addLayout(form)
        self.startup=QCheckBox('登录 Windows 后自动启动 Lumen');self.startup.setObjectName('windowsStartup')
        self.startup_status=note('');self.startup_status.setObjectName('windowsStartupStatus')
        form.addRow('开机自启动',self.startup);form.addRow(self.startup_status)
        self.refresh_startup();self.startup.toggled.connect(self.change_startup)
        self._silent_state=self.library.setting(startup.SILENT_START_SETTING,False) is True
        self.silent_startup=QCheckBox('静默启动（仅显示托盘，不打开主窗口）');self.silent_startup.setObjectName('windowsSilentStartup')
        self.silent_startup.setChecked(self._silent_state)
        reason=startup.unavailable_reason();self.silent_startup.setEnabled(not reason)
        form.addRow('启动方式',self.silent_startup)
        self.silent_status=note(reason or '开机自启动始终在后台待机。此开关同时控制双击快捷方式的首次启动；下次启动生效。')
        self.silent_status.setObjectName('windowsSilentStartupStatus');form.addRow(self.silent_status)
        self.silent_startup.toggled.connect(self.change_silent_start)
        behavior=note('关闭窗口后');behavior.setObjectName('sectionTitle');outer.addWidget(behavior)
        outer.addWidget(note('关闭主窗口后继续在托盘运行，已开启的局域网服务和目录监听继续可用。'))
        outer.addWidget(note('打开主窗口：双击托盘图标、右键选择“打开 Lumen”，或再次运行快捷方式。'))
        outer.addWidget(note('完全退出：托盘图标右键 → 退出 Lumen。取消菜单或点击菜单外部会保留托盘和后台服务。'))
        outer.addStretch()

    def refresh_startup(self):
        self._startup_state=startup.status(self.library.directory.resolve())
        with QSignalBlocker(self.startup):self.startup.setChecked(self._startup_state.enabled)
        self.startup.setEnabled(self._startup_state.supported)
        self.startup_status.setText(self._startup_state.description)

    def change_startup(self,enabled):
        previous=self._startup_state
        try:startup.set_enabled(self.library.directory.resolve(),enabled)
        except startup.StartupError as error:
            self.refresh_startup()
            if not self._startup_state.supported:
                with QSignalBlocker(self.startup):self.startup.setChecked(previous.enabled)
            QMessageBox.warning(self,'未保存自启动设置',str(error));return
        self.refresh_startup()

    def change_silent_start(self,enabled):
        if not self.silent_startup.isEnabled():
            with QSignalBlocker(self.silent_startup):self.silent_startup.setChecked(self._silent_state)
            return
        try:self.library.set_setting(startup.SILENT_START_SETTING,bool(enabled))
        except (sqlite3.Error,OSError,ValueError) as error:
            with QSignalBlocker(self.silent_startup):self.silent_startup.setChecked(self._silent_state)
            QMessageBox.warning(self,'未保存静默启动设置',str(error));return
        self._silent_state=bool(enabled)
        self.silent_status.setText('已保存，下次首次启动生效。双击托盘或再次运行快捷方式可打开主窗口。')
