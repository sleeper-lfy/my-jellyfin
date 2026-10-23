"""Nonblocking Windows update controls shared by Settings and the update window."""
from dataclasses import asdict
import json
from pathlib import Path
import time
from PySide6.QtCore import QObject,Signal,Slot,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QProgressBar,QPlainTextEdit,QDialog,QApplication
from . import __version__,updates
from .background import run_background
from .core import Library,check_cancelled


class UpdatePanel(QWidget):
    def __init__(self,controller,parent=None):
        super().__init__(parent);self.controller=controller;layout=QVBoxLayout(self)
        heading=QLabel('当前版本 '+__version__);layout.addWidget(heading)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,1000);layout.addWidget(self.progress)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);self.notes.setMaximumHeight(180);layout.addWidget(self.notes)
        buttons=QHBoxLayout();self.check=QPushButton('检查更新');self.download=QPushButton('下载新版');self.install=QPushButton('安装并重启');self.cancel=QPushButton('取消下载')
        for button in (self.check,self.download,self.install,self.cancel):buttons.addWidget(button)
        layout.addLayout(buttons);self.check.clicked.connect(controller.check);self.download.clicked.connect(controller.download);self.install.clicked.connect(controller.install);self.cancel.clicked.connect(controller.cancel)
        self.options={}
        for key,title,default in (('check','自动检查更新（每天一次）',True),('download','自动下载已校验的新版本',False),('install','空闲时自动安装并重启',False)):
            box=QCheckBox(title);box.setChecked(controller.window.library.setting('updates:'+key,default));self.options[key]=box
            box.toggled.connect(lambda checked,key=key:controller.option(key,checked));layout.addWidget(box)
        self.options['install'].setEnabled(updates.can_install())
        notice=QLabel('更新来自 GitHub Releases。下载后核对大小、SHA-256 和 Windows 程序格式。自动安装等待导入、后台任务、PC / 手机播放结束，并先备份资料库；原媒体和资料库目录保留。' if updates.can_install() else '自动安装适用于打包后的 Windows 客户端；源码运行可检查和下载安装包，更新源码请使用 Git。')
        notice.setWordWrap(True);layout.addWidget(notice);layout.addStretch()
        controller.changed.connect(self.render);self.render(controller.state())
    @Slot(object)
    def render(self,state):
        self.status.setText(state['message']);self.progress.setValue(state['progress']);self.progress.setVisible(state['busy']);
        if self.notes.toPlainText()!=state['notes']:self.notes.setPlainText(state['notes'])
        self.notes.setVisible(bool(state['notes']))
        self.check.setEnabled(not state['busy']);self.download.setEnabled(not state['busy'] and state['candidate']);self.install.setEnabled(not state['busy'] and state['staged'] and updates.can_install());self.cancel.setEnabled(state['downloading'])
        for key,box in self.options.items():
            box.blockSignals(True);box.setChecked(self.controller.window.library.setting('updates:'+key,key=='check'));box.blockSignals(False)


class DesktopUpdates(QObject):
    changed=Signal(object)
    def __init__(self,window):
        super().__init__(window);self.window=window;self.directory=window.library.directory/'updates';self.candidate=None;self.staged=None;self.busy=False;self.downloading=False;self.worker=None;self.dialog=None;self.progress=0;self.message='点击检查更新，或启用启动时自动检查。';self.failed_version='';self.restoring=True;self.check_requested=False
        self.restore()
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(self.maybe_install);self.timer.start()
        self.check_timer=QTimer(self);self.check_timer.setInterval(3600000);self.check_timer.timeout.connect(self.startup);self.check_timer.start()
    def state(self):return {'message':self.message,'progress':self.progress,'busy':self.busy,'downloading':self.downloading,'candidate':self.candidate is not None,'staged':self.staged is not None,'notes':self.candidate.notes if self.candidate else ''}
    def notify(self,message=None):
        if message is not None:self.message=message
        self.changed.emit(self.state())
    def option(self,key,enabled):
        self.window.library.set_setting('updates:'+key,enabled)
        if key=='install' and enabled:self.window.library.set_setting('updates:download',True)
        self.notify();self.maybe_install()
    def panel(self,parent=None):return UpdatePanel(self,parent)
    def show(self):
        if self.dialog is None:
            self.dialog=QDialog(self.window);self.dialog.setWindowTitle('软件更新 · Lumen');self.dialog.resize(650,560);layout=QVBoxLayout(self.dialog);layout.addWidget(self.panel());close=QPushButton('关闭');close.clicked.connect(self.dialog.close);layout.addWidget(close)
        self.dialog.show();self.dialog.raise_()
    def restore(self):
        self.busy=True;self.notify('正在读取已下载的更新…')
        def read(job):
            metadata=self.directory/'staged.json';outcome=self.directory/'update-result.json';failed=''
            if outcome.is_file() and outcome.stat().st_size<65536:
                data=json.loads(outcome.read_text(encoding='utf-8-sig'))
                if not data.get('ok'):failed=data.get('version','')
            if metadata.is_file() and metadata.stat().st_size<65536:
                candidate=updates.Candidate(**json.loads(metadata.read_text(encoding='utf-8')))
                if updates.version(candidate.version)>updates.version(__version__):
                    path=self.directory/f'Lumen-Setup-{candidate.version}-x64.exe'
                    updates.verify(path,candidate,job.isInterruptionRequested);return candidate,path,failed
            return None,None,failed
        def restored(data):
            self.restoring=self.busy=False;self.candidate,self.staged,self.failed_version=data
            self.notify('上次安装失败，可手动重试；详情见 updates/update-install.log。' if self.failed_version else '已恢复校验过的更新，可安装并重启。' if self.staged else '点击检查更新，或启用启动时自动检查。')
            if self.check_requested:self.check_requested=False;self.check()
        def failed(_error):
            self.restoring=self.busy=False;self.notify('缓存更新不可用，请重新检查更新。')
            if self.check_requested:self.check_requested=False;self.check()
        self.worker=run_background(self.window,read,restored,failed)
    def startup(self):
        if self.window._closing:return
        if self.window.library.setting('updates:check',True) and time.time()-self.window.library.setting('updates:last_check',0)>=86400:self.check()
    def check(self):
        if self.restoring:self.check_requested=True;return
        if self.busy or self.window._closing:return
        self.busy=True;self.progress=0;self.notify('正在后台检查 GitHub 更新…');proxy=self.window.library.setting('proxy','')
        def checked(candidate):
            self.busy=False
            if self.candidate!=candidate:self.staged=None
            self.candidate=candidate
            self.notify('未发现可用的更高版本安装包。' if candidate is None else '发现新版 '+candidate.version)
            if candidate and self.window.library.setting('updates:download',False):self.download()
        def read(job):
            candidate=updates.check(__version__,lambda url,limit:updates.fetch(url,limit,proxy,job.isInterruptionRequested),job.isInterruptionRequested)
            import sqlite3
            library=Library(self.window.library.directory,initialize=False)
            try:
                library.db.execute('PRAGMA busy_timeout=300')
                try:library.set_setting('updates:last_check',time.time())
                except sqlite3.OperationalError:pass
            finally:library.close()
            return candidate
        self.worker=run_background(self.window,read,checked,self.failed)
    def failed(self,error):
        if self.staged and self.candidate:self.failed_version=self.candidate.version
        self.busy=False;self.downloading=False;self.notify('更新失败，可重试：'+error)
    def cancel(self):
        if self.worker and self.downloading:self.worker.requestInterruption();self.notify('正在取消下载…')
    def download(self):
        if self.busy or self.candidate is None or self.window._closing:return
        candidate=self.candidate;proxy=self.window.library.setting('proxy','');self.busy=self.downloading=True;self.progress=0;self.notify('正在后台下载 '+candidate.version+'…')
        def transfer(job):
            destination=self.directory/f'Lumen-Setup-{candidate.version}-x64.exe'
            if destination.is_file():
                try:return updates.verify(destination,candidate,job.isInterruptionRequested)
                except (ValueError,OSError):pass
            return updates.download(candidate,self.directory,job.progress.emit,job.isInterruptionRequested,proxy=proxy)
        def downloaded(path):
            self.busy=self.downloading=False;self.staged=path;self.progress=1000;self.notify('下载完成，大小、SHA-256 和 PE 格式已核对。可安装并重启。')
            metadata=self.directory/'staged.json';metadata.write_text(json.dumps(asdict(candidate)),encoding='utf-8')
            self.maybe_install()
        job=self.worker=run_background(self.window,transfer,downloaded,self.failed);job.progress.connect(self.download_progress)
        def finished():
            if self.worker is job and self.downloading:self.busy=self.downloading=False;self.notify('下载已取消，临时文件已清理。')
        job.finished.connect(finished)
    @Slot(object,object)
    def download_progress(self,done,total):self.progress=done*1000//max(1,total);self.notify(f'下载 {done/1048576:.1f} / {total/1048576:.1f} MiB · {done*100//max(1,total)}%')
    def idle(self,automatic=False,ignore=None):
        window=self.window
        if window._closing or window.task_budget.active or window.jobs or window.job_queue or window._browse_job or window._auxiliary_jobs-({ignore} if ignore else set()) or (window.player.isVisible() and window.player.file):return False
        if automatic and QApplication.activeModalWidget() is not None:return False
        server=window.lan_server
        if server:
            if not server.lock.acquire(blocking=False):return False
            try:
                if any(server.clock()-record['time']<30 for record in server.sessions.values()):return False
            finally:server.lock.release()
            downloads=getattr(server,'downloads',None)
            if downloads:
                if not downloads.lock.acquire(blocking=False):return False
                try:
                    if downloads.active:return False
                finally:downloads.lock.release()
        return True
    def maybe_install(self):
        if updates.can_install() and not self.busy and self.staged and self.window.library.setting('updates:install',False) and self.failed_version!=self.candidate.version and self.idle(True):self.install(automatic=True)
    def install(self,automatic=False):
        if self.busy or not self.staged:return
        if not updates.can_install():self.notify('自动安装仅支持打包后的 Windows 客户端。');return
        if not self.idle():self.notify('更新已就绪。请先结束播放、导入与后台任务，自动安装会在空闲时继续。');return
        candidate=self.candidate;installer=self.staged;directory=self.window.library.directory
        self.busy=True;self.notify('正在备份资料库并准备更新…')
        def prepare(job):
            updates.verify(installer,candidate,job.isInterruptionRequested);check_cancelled(job.isInterruptionRequested)
            library=Library(directory,initialize=False)
            try:library.backup(self.directory/f'library-before-{candidate.version}-{int(time.time())}.sqlite')
            finally:library.close()
            check_cancelled(job.isInterruptionRequested)
            return updates.prepare_installer(candidate,installer,directory)
        def prepared(plan):
            if self.window._closing:return
            if automatic and not self.window.library.setting('updates:install',False):
                self.busy=False;self.notify('已关闭自动安装，安装包已保留。');return
            if not self.idle(automatic,ignore=self.worker):
                self.busy=False;self.notify('有新任务或播放开始，已暂缓安装；请空闲后重试。');return
            try:updates.launch_installer(plan)
            except OSError as error:self.failed(str(error));return
            self.window._update_pending=True
            for widget in QApplication.topLevelWidgets():
                if widget is not self.window and widget is not self.window.player:widget.close()
            self.window.close()
        self.worker=run_background(self.window,prepare,prepared,self.failed)
