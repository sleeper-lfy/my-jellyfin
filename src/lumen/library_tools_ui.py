"""Directory monitoring and read-only library health reports."""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QPushButton,QFileDialog,QInputDialog,QCheckBox,QSpinBox,QPlainTextEdit,QTabWidget,QWidget,QMessageBox
from .media_tools import audit_library


class LibraryTools(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.library=window.library;self.setWindowTitle('目录监控与媒体库体检');self.resize(850,650)
        layout=QVBoxLayout(self);tabs=QTabWidget();layout.addWidget(tabs)
        monitor=QWidget();content=QVBoxLayout(monitor);tabs.addTab(monitor,'目录自动监控')
        note=QLabel('程序运行时每 10 秒检查已启用目录；文件和 NFO / 图片稳定后再增量入库。\n离线目录保留资料，监控不移动或删除原文件。');note.setWordWrap(True);content.addWidget(note)
        self.folders=self.library.setting('watched_folders',[]);self.list=QListWidget();content.addWidget(self.list)
        row=QHBoxLayout();content.addLayout(row)
        for title,action in [('添加目录',self.add),('启用 / 暂停',self.toggle),('移除监控',self.remove)]:
            control=QPushButton(title);control.clicked.connect(action);row.addWidget(control)
        self.quiet=QSpinBox();self.quiet.setRange(5,600);self.quiet.setValue(self.library.setting('watch_settle_seconds',15));self.quiet.setSuffix(' 秒稳定等待')
        content.addWidget(self.quiet)
        save=QPushButton('保存监控设置');save.clicked.connect(self.save);content.addWidget(save)
        self.reload()
        health=QWidget();health_layout=QVBoxLayout(health);tabs.addTab(health,'媒体库体检')
        explanation=QLabel('检查离线目录、失效路径、缺失海报、损坏 NFO 和已确认的重复指纹。只生成报告。');explanation.setWordWrap(True);health_layout.addWidget(explanation)
        self.report=QPlainTextEdit();self.report.setReadOnly(True);health_layout.addWidget(self.report)
        self.render(self.library.setting('last_audit',{}))
        scan=QPushButton('开始后台体检');scan.clicked.connect(lambda:window.run_job('媒体库体检',lambda lib,p:audit_library(lib,p,p.cancelled),self.render));health_layout.addWidget(scan)
        export=QPushButton('导出体检报告…');export.clicked.connect(self.export);health_layout.addWidget(export)
    def reload(self):
        self.list.clear()
        from .ui import KINDS
        kinds=KINDS
        for entry in self.folders:self.list.addItem(('启用' if entry.get('enabled',True) else '暂停')+' · '+kinds.get(entry['kind'],entry['kind'])+' · '+entry['path'])
    def add(self):
        path=QFileDialog.getExistingDirectory(self,'选择监控目录')
        if not path:return
        from .ui import KINDS
        names={title:kind for kind,title in KINDS.items()}
        kind,ok=QInputDialog.getItem(self,'媒体类型','此目录作为',list(names),0,False)
        if not ok:return
        target=Path(path).resolve()
        if any(target.is_relative_to(Path(row['path']).resolve()) or Path(row['path']).resolve().is_relative_to(target) for row in self.folders):QMessageBox.information(self,'目录范围重叠','同一目录及其子目录不能重复监控，请调整已有监控范围');return
        self.folders.append({'path':str(Path(path).resolve()),'kind':names[kind],'enabled':True});self.reload()
    def toggle(self):
        index=self.list.currentRow()
        if index>=0:self.folders[index]['enabled']=not self.folders[index].get('enabled',True);self.reload()
    def remove(self):
        index=self.list.currentRow()
        if index>=0:self.folders.pop(index);self.reload()
    def save(self):
        for row in self.folders:row['settle_seconds']=self.quiet.value()
        self.library.set_setting('watched_folders',self.folders);self.library.set_setting('watch_settle_seconds',self.quiet.value())
        self.window.status.setText('目录监控设置已保存，稳定文件将在后续检查中入库')
    def render(self,value):
        if self.isVisible() or hasattr(self,'report'):
            labels={'directory_offline':'目录离线','file_missing':'文件缺失','outside_root':'路径超出根目录','missing_cover':'缺失海报','invalid_nfo':'NFO 损坏'}
            lines=[f"已检查 {value.get('checked',0)} 个文件，发现 {len(value.get('issues',[]))} 个问题"]
            lines.extend(f"{labels.get(row['kind'],row['kind'])} · {row.get('title','')}\n{row['path']}\n{row.get('reason','')}" for row in value.get('issues',[]))
            lines.extend('相同 SHA-256 文件：'+str(row['file_ids']) for row in value.get('duplicates',[]))
            self.report.setPlainText('\n\n'.join(lines))
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'导出体检报告','lumen-library-health.json','JSON (*.json)')
        if path:Path(path).write_text(json.dumps(self.library.setting('last_audit',{}),ensure_ascii=False,indent=2),encoding='utf-8')
