"""Directory monitoring and read-only library health reports."""
import json
import copy
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QPushButton,QInputDialog,QCheckBox,QSpinBox,QPlainTextEdit,QTabWidget,QWidget,QMessageBox,QComboBox,QLineEdit,QFormLayout,QDialogButtonBox,QScrollArea
from .media_tools import audit_library


class LibraryTools(QDialog):
    def __init__(self,window,embedded=False):
        super().__init__(window);self.window=window;self.library=window.library;self.setWindowTitle('媒体目录与自动入库');self.resize(850,650)
        self.embedded=embedded;self._allow_close=False
        if embedded:self.setWindowFlags(Qt.WindowType.Widget)
        self.naming_updates={};layout=QVBoxLayout(self);self.tabs=QTabWidget()
        if not embedded:layout.addWidget(self.tabs)
        monitor=QWidget();content=QVBoxLayout(monitor)
        if embedded:layout.addWidget(monitor)
        else:self.tabs.addTab(monitor,'目录与入库')
        top=QHBoxLayout();content.addLayout(top)
        from .ui import KINDS
        self.kind_filter=QComboBox();self.kind_filter.addItem('全部分类','')
        for kind,title in KINDS.items():self.kind_filter.addItem(title,kind)
        self.kind_filter.setCurrentIndex(max(0,self.kind_filter.findData(window.section)))
        top.addWidget(self.kind_filter,1)
        refresh=QPushButton('立即刷新当前分类');refresh.setObjectName('refreshCategoryDirectories');refresh.clicked.connect(lambda:self.refresh_directories(False));top.addWidget(refresh)
        content.addWidget(self._note('稳定的新视频自动入库；缺失记录经确认后清理。离线目录保留资料。自动监听需要应用运行。'))
        self.folders=copy.deepcopy(self.library.setting('watched_folders',[]));self.list=QListWidget();self.list.setMinimumHeight(90);self.list.setMaximumHeight(150);content.addWidget(self.list,1)
        self.kind_filter.currentIndexChanged.connect(self.reload);self.list.currentRowChanged.connect(self.selection_changed)
        row=QHBoxLayout();content.addLayout(row);self.context_controls=[]
        for title,action,selected in [('添加目录',self.add,False),('目录详情 / 规则',self.edit_rule,True),('启用 / 暂停',self.toggle,True),('移除监控',self.remove,True)]:
            control=QPushButton(title);control.clicked.connect(action);row.addWidget(control)
            if selected:self.context_controls.append(control)
        self.list.itemDoubleClicked.connect(lambda _:self.edit_rule())
        self.summary=QPlainTextEdit();self.summary.setObjectName('selectedDirectorySummary');self.summary.setReadOnly(True);self.summary.setMaximumHeight(100);self.summary.setPlaceholderText('选择目录后查看实际使用的来源、目标和命名规则。');content.addWidget(self.summary)
        presets=QHBoxLayout();content.addLayout(presets)
        self.vr_button=QPushButton('VR 目录播放预设…');self.vr_button.clicked.connect(self.vr_preset);presets.addWidget(self.vr_button)
        self.refresh_selected=QPushButton('刷新选中目录');self.refresh_selected.clicked.connect(lambda:self.refresh_directories(True));presets.addWidget(self.refresh_selected);self.context_controls.append(self.refresh_selected)
        self.quiet=QSpinBox();self.quiet.setRange(5,600);self.quiet.setValue(self.library.setting('watch_settle_seconds',15));self.quiet.setSuffix(' 秒稳定等待')
        self.quiet.valueChanged.connect(self.mark_dirty)
        save_row=QHBoxLayout();save_row.addWidget(self.quiet);save=QPushButton('保存目录设置');save.setObjectName('saveDirectorySettings');save.clicked.connect(self.save);save_row.addWidget(save);content.addLayout(save_row)
        self.sync_status=self._note('新增、暂停、移除与规则编辑暂存为草稿；保存后生效。');content.addWidget(self.sync_status)
        self.reload()
        if not embedded:
            health=QWidget();health_layout=QVBoxLayout(health);self.tabs.addTab(health,'文件与路径体检')
            health_layout.addWidget(self._note('检查离线目录、失效路径、缺失海报、损坏 NFO 和已确认的重复指纹。这里只生成报告；修复资料请使用媒体管理中的资料补全。'))
            self.report=QPlainTextEdit();self.report.setReadOnly(True);health_layout.addWidget(self.report)
            self.render(self.library.setting('last_audit',{}))
            scan=QPushButton('开始后台体检');scan.clicked.connect(lambda:window.run_job('媒体库体检',lambda lib,p:audit_library(lib,p,p.cancelled),self.render));health_layout.addWidget(scan)
            export=QPushButton('导出体检报告…');export.clicked.connect(self.export);health_layout.addWidget(export)
    @staticmethod
    def _note(text):
        label=QLabel(text);label.setWordWrap(True);return label
    def has_changes(self):
        return bool(self.naming_updates or self.folders!=self.library.setting('watched_folders',[]) or self.quiet.value()!=self.library.setting('watch_settle_seconds',15))
    def mark_dirty(self,*args):
        if hasattr(self,'sync_status') and self.has_changes():self.sync_status.setText('有未保存的目录更改；点击“保存目录设置”生效。')
    def confirm_discard(self):
        if (not self.embedded and not self.isVisible()) or not self.has_changes():return True
        return QMessageBox.question(self,'未保存的目录设置','目录更改尚未保存。是否放弃这些更改并关闭？',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
    def reject(self):
        if self._allow_close or self.confirm_discard():super().reject()
    def closeEvent(self,event):
        if self.confirm_discard():
            self._allow_close=True
            try:super().closeEvent(event)
            finally:self._allow_close=False
        else:event.ignore()
    def selection_changed(self,*args):
        index=self.selected_index();selected=index>=0
        for control in self.context_controls:control.setEnabled(selected)
        self.vr_button.setEnabled(selected and self.folders[index]['kind']=='vr')
        if not selected:self.summary.clear();return
        from .media_management_ui import describe_directory_rule
        self.summary.setPlainText(describe_directory_rule(self.library,self.folders[index],self.naming_updates))
    def reload(self):
        selected=self.selected_index()
        self.list.clear()
        from .ui import KINDS
        kinds=KINDS
        for index,entry in enumerate(self.folders):
            if self.kind_filter.currentData() and entry['kind']!=self.kind_filter.currentData():continue
            self.list.addItem(('启用' if entry.get('enabled',True) else '暂停')+' · '+kinds.get(entry['kind'],entry['kind'])+' · '+entry['path'])
            self.list.item(self.list.count()-1).setData(Qt.ItemDataRole.UserRole,index)
            if index==selected:self.list.setCurrentRow(self.list.count()-1)
        self.selection_changed();self.mark_dirty()
    def selected_index(self):
        item=self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else -1
    def add(self):
        from .dialogs import existing_directory
        path=existing_directory(self,'选择监控目录')
        if not path:return
        from .ui import KINDS
        names={title:kind for kind,title in KINDS.items()}
        kind,ok=QInputDialog.getItem(self,'媒体类型','此目录作为',list(names),max(0,list(names.values()).index(self.kind_filter.currentData()) if self.kind_filter.currentData() else 0),False)
        if not ok:return
        target=Path(path).resolve()
        if any(target.is_relative_to(Path(row['path']).resolve()) or Path(row['path']).resolve().is_relative_to(target) for row in self.folders):QMessageBox.information(self,'目录范围重叠','同一目录及其子目录不能重复监控，请调整已有监控范围');return
        self.folders.append({'path':str(Path(path).resolve()),'kind':names[kind],'enabled':True});self.reload()
    def edit_rule(self):
        index=self.selected_index()
        if index<0:return
        from .media_management_ui import DirectoryRuleDialog
        dialog=DirectoryRuleDialog(self.window,self.folders[index],self.naming_updates,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        self.folders[index]=dialog.entry;self.naming_updates.update(dialog.naming_update);self.reload()

    def vr_preset(self):
        index=self.selected_index()
        if index<0:QMessageBox.information(self,'选择目录','请先选择要配置播放预设的目录。');return
        from .vr_presets_ui import show_vr_presets
        show_vr_presets(self.window,self.folders[index]['path'])

    def naming_rule(self):
        # Compatibility entry; the directory editor makes target scope explicit.
        self.edit_rule()

    def toggle(self):
        index=self.selected_index()
        if index>=0:self.folders[index]['enabled']=not self.folders[index].get('enabled',True);self.reload()
    def remove(self):
        index=self.selected_index()
        if index>=0:self.folders.pop(index);self.reload()
    def save(self):
        from .media_libraries import list_libraries, overlaps
        for item in list_libraries(self.library):
            paths=[r['path'] for r in item['config']['roots']]+([item['config']['destination']] if item['config']['destination'] else [])
            if any(overlaps(str(Path(row['path']).resolve()),path) for row in self.folders for path in paths):
                self.sync_status.setText('目录与自定义媒体库“'+item['name']+'”重叠，请在媒体库管理中配置。');return
        for row in self.folders:row['settle_seconds']=self.quiet.value()
        old=self.library.setting('watched_folders',[])
        moving=[row for row in self.folders if row.get('enabled',True) and row['kind'] in {'movie','series','vr'} and row.get('destination',self.library.setting('partition:'+row['kind'],{}).get('destination',''))]
        if moving and old!=self.folders and QMessageBox.question(self,'启用目录自动整理','这些目录的新文件将按规则自动移动。是否保存？')!=QMessageBox.StandardButton.Yes:return
        from .media_management_ui import write_settings
        write_settings(self.library,{'watched_folders':self.folders,'watch_settle_seconds':self.quiet.value(),**self.naming_updates})
        self.naming_updates.clear();self.selection_changed();self.sync_status.setText('目录设置已保存；手动刷新会扫描上方分类或选中目录。')
        self.window.status.setText('目录监控设置已保存，稳定文件将在后续检查中入库')
    def refresh_directories(self,selected=False):
        from .directory_sync import scan_directories,remove_missing
        if self.folders!=self.library.setting('watched_folders',[]) or self.naming_updates:
            QMessageBox.information(self,'先保存目录','请先保存监控设置，再刷新目录。');return
        index=self.selected_index();kind=self.kind_filter.currentData()
        configs=([self.folders[index]] if index>=0 else []) if selected else [entry for entry in self.folders if not kind or entry['kind']==kind]
        if not configs:
            self.sync_status.setText('请先为此分类添加并保存目录，或选中一个目录。');return
        import copy
        configs=copy.deepcopy(configs)
        self.sync_status.setText('目录刷新已加入后台队列…')
        def ready(result):
            if not self.isVisible():return
            summary=f"新增 {result['imported']} · 资料更新 {result['updated']} · 等待文件稳定 {result['waiting']} · 缺失 {len(result['missing'])} · 不可用目录 {len(result['offline'])} · 导入失败 {len(result['errors'])}"
            self.sync_status.setText(summary)
            if result['missing']:
                question=QMessageBox(self);question.setWindowTitle('同步缺失视频')
                question.setText(summary+'\n是否移除这些缺失视频的媒体库记录及对应播放历史？不会删除磁盘文件。')
                question.setDetailedText('\n'.join(entry['path'] for entry in result['missing']))
                question.setStandardButtons(QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel)
                question.button(QMessageBox.StandardButton.Ok).setText('移除缺失记录');question.button(QMessageBox.StandardButton.Cancel).setText('保留记录')
                if question.exec()==QMessageBox.StandardButton.Ok:
                    def done(value):
                        if self.isVisible():self.sync_status.setText(f"已移除 {value['removed']} 条缺失记录 · 路径恢复、离线或播放中而跳过 {value['skipped']} 条")
                    self.window.run_job('同步移除缺失记录',lambda lib,p:remove_missing(lib,result['missing'],p.cancelled),done)
            if result['offline'] or result['errors']:
                self.sync_status.setToolTip('\n'.join(str(entry) for entry in result['offline']+result['errors']))
        self.window.run_job('刷新媒体目录',lambda lib,p:scan_directories(lib,configs,p,p.cancelled),ready)

    def render(self,value):
        if self.isVisible() or hasattr(self,'report'):
            labels={'directory_offline':'目录离线','file_missing':'文件缺失','outside_root':'路径超出根目录','missing_cover':'缺失海报','invalid_nfo':'NFO 损坏'}
            lines=[f"已检查 {value.get('checked',0)} 个文件，发现 {len(value.get('issues',[]))} 个问题"]
            lines.extend(f"{labels.get(row['kind'],row['kind'])} · {row.get('title','')}\n{row['path']}\n{row.get('reason','')}" for row in value.get('issues',[]))
            lines.extend('相同 SHA-256 文件：'+str(row['file_ids']) for row in value.get('duplicates',[]))
            self.report.setPlainText('\n\n'.join(lines))
    def export(self):
        from .dialogs import save_file_name
        path=save_file_name(self,'导出体检报告','lumen-library-health.json','JSON (*.json)')
        if path:Path(path).write_text(json.dumps(self.library.setting('last_audit',{}),ensure_ascii=False,indent=2),encoding='utf-8')
