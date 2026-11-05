"""One place for media folders, effective ingestion rules and library maintenance."""
import copy
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QScrollArea, QLabel, QComboBox, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QCheckBox, QDialogButtonBox, QMessageBox)
from .plugins import Plugins
from .organize_templates import rule_key, validate_rule

KINDS = {'movie':'电影', 'series':'电视剧', 'vr':'VR 电影', 'fans':'Fans', 'other':'其他视频'}
FILMS = {'movie', 'series', 'vr'}


def note(text):
    widget = QLabel(text); widget.setTextFormat(Qt.TextFormat.PlainText); widget.setWordWrap(True); widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def scroll_form(layout):
    scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget(); content = QVBoxLayout(body); scroll.setWidget(body); layout.addWidget(scroll, 1)
    return content


def write_settings(library, values):
    """Commit a related set of configuration changes together; None removes an override."""
    with library.db:
        for key, value in values.items():
            if value is None: library.db.execute('DELETE FROM settings WHERE key=?', (key,))
            else: library.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))


def effective_directory_rule(library, entry, overrides=None):
    kind = entry['kind']; default = library.setting('partition:' + kind, {})
    plugin = entry.get('plugin', default.get('plugin', '')) if kind in FILMS else ''
    destination = entry.get('destination', default.get('destination', '')) if kind in FILMS else ''
    naming_key = rule_key(kind, destination) if destination else None
    stored = (overrides or {}).get(naming_key, library.setting(naming_key, None)) if naming_key else None
    naming = stored if stored is not None else library.setting(rule_key(kind), {'folder':'', 'filename':''})
    return {'kind':kind, 'path':entry['path'], 'plugin':plugin, 'destination':destination,
            'plugin_inherited':'plugin' not in entry, 'destination_inherited':'destination' not in entry,
            'fallbacks':library.setting('numbered_fallbacks:' + kind, []) if plugin else [],
            'naming':naming, 'naming_key':naming_key, 'naming_inherited':stored is None}


def describe_directory_rule(library, entry, overrides=None):
    rule = effective_directory_rule(library, entry, overrides)
    providers = {p['id']:p['name'] for p in Plugins(library).installed()}
    source = providers.get(rule['plugin'], rule['plugin']) or '不自动刮削'
    fallback = ' → '.join(providers.get(p, p) for p in rule['fallbacks'] if p != rule['plugin']) or '无'
    naming_scope = '分类默认' if rule['naming_inherited'] else '整理目标目录专用（同目标目录共用）'
    return '\n'.join([
        '媒体类型：' + KINDS.get(rule['kind'], rule['kind']), '监听源目录：' + rule['path'],
        '首选来源：' + source + ('（继承分类）' if rule['plugin_inherited'] else '（此目录覆盖）'),
        '备用来源：' + fallback + '（分类顺序）',
        '整理目标：' + (rule['destination'] or '保留原位置') + ('（继承分类）' if rule['destination_inherited'] else '（此目录覆盖）'),
        '命名规则：' + naming_scope, '目录模板：' + (rule['naming'].get('folder') or '标题（年份）'),
        '文件名模板：' + (rule['naming'].get('filename') or '保留原文件名')])


def add_provider_items(combo, library, selected, inherit=False, kind=None):
    if inherit: combo.addItem('继承分类默认来源', None)
    combo.addItem('不自动刮削', '')
    for provider in Plugins(library).installed():
        if provider['config'].get('enabled') and 'search' in provider['capabilities'] \
                and (kind is None or not provider.get('media_kinds') or kind in provider['media_kinds']):
            combo.addItem(provider['name'], provider['id'])
    if selected and combo.findData(selected) < 0: combo.addItem(selected + '（当前不可用）', selected)
    combo.setCurrentIndex(max(0, combo.findData(selected)))


class CategoryRules(QWidget):
    """The only editor for category source order, destination and naming defaults."""
    def __init__(self, window, changed=None, allow_sources=True):
        super().__init__(); self.window=window; self.library=window.library; self.changed=changed
        outer=QVBoxLayout(self); content=scroll_form(outer)
        content.addWidget(note('分类默认规则供监听目录和手动导入继承。目录的单独设置优先；这里只影响后续入库和整理。'))
        form=QFormLayout(); content.addLayout(form)
        self.kind=QComboBox(); self.kind.setObjectName('ruleCategory')
        for key,title in KINDS.items(): self.kind.addItem(title,key)
        self.kind.setCurrentIndex(max(0,self.kind.findData(window.section)))
        form.addRow('媒体分类',self.kind)
        self.primary=QComboBox(); self.primary.setObjectName('categoryPrimary'); form.addRow('首选刮削来源',self.primary)
        self.fallbacks=QListWidget(); self.fallbacks.setObjectName('categoryFallbacks'); self.fallbacks.setMinimumHeight(95); self.fallbacks.setMaximumHeight(150)
        content.addWidget(note('备用来源：勾选后从上到下尝试，最多 7 个。未启用首选来源时不会自动刮削。')); content.addWidget(self.fallbacks)
        order=QHBoxLayout(); content.addLayout(order)
        for title,delta in [('上移',-1),('下移',1)]:
            button=QPushButton(title); button.clicked.connect(lambda checked=False,delta=delta:self.move(delta)); order.addWidget(button)
        self.destination=QLineEdit(); self.destination.setObjectName('categoryDestination'); self.destination.setPlaceholderText('留空保留原位置')
        destination_row=QHBoxLayout(); destination_row.addWidget(self.destination)
        browse=QPushButton('选择整理目标…'); browse.clicked.connect(self.browse); destination_row.addWidget(browse)
        content.addWidget(note('分类默认整理目标')); content.addLayout(destination_row)
        content.addWidget(note('分类默认命名模板（目标目录有专用模板时，优先使用目标目录规则）'))
        from .organize_ui import RuleFields
        self.naming=RuleFields(content, {})
        self.status=note(''); content.addWidget(self.status); content.addStretch()
        actions=QHBoxLayout();outer.addLayout(actions)
        save=QPushButton('保存分类规则'); save.setObjectName('saveCategoryRules'); save.clicked.connect(self.save); actions.addWidget(save)
        sources=QPushButton('来源安装 / 检测…'); sources.clicked.connect(window.numbered_sources); sources.setVisible(allow_sources); actions.addWidget(sources)
        reload=QPushButton('重新读取');reload.setToolTip('重新读取已启用来源及此分类的已保存配置'); reload.clicked.connect(self.request_reload); actions.addWidget(reload)
        self.kind.currentIndexChanged.connect(self.kind_changed); self.reload()
    def signature(self):
        return (self.primary.currentData(),self.destination.text(),self.naming.folder.text(),self.naming.filename.text(),
            tuple((self.fallbacks.item(i).data(Qt.ItemDataRole.UserRole),self.fallbacks.item(i).checkState()) for i in range(self.fallbacks.count())))
    def has_changes(self):
        return hasattr(self,'loaded') and self.signature()!=self.loaded
    def discard_prompt(self):
        return not self.has_changes() or QMessageBox.question(self,'未保存的分类规则','是否放弃当前分类尚未保存的更改？',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
    def request_reload(self):
        if self.discard_prompt():self.reload()
    def kind_changed(self):
        if self.discard_prompt():self.reload()
        else:
            self.kind.blockSignals(True);self.kind.setCurrentIndex(self.kind.findData(self.loaded_kind));self.kind.blockSignals(False)
    def browse(self):
        from .dialogs import existing_directory
        path=existing_directory(self,'选择分类默认整理目标',self.destination.text())
        if path:self.destination.setText(path)
    def move(self,delta):
        index=self.fallbacks.currentRow(); target=index+delta
        if index>=0 and 0<=target<self.fallbacks.count():
            item=self.fallbacks.takeItem(index); self.fallbacks.insertItem(target,item); self.fallbacks.setCurrentItem(item)
    def reload(self):
        kind=self.kind.currentData(); rule=self.library.setting('partition:'+kind,{})
        self.primary.clear(); add_provider_items(self.primary,self.library,rule.get('plugin',''),kind=self.kind.currentData())
        # A source needs search only; the ingestion pipeline skips the detail step for search-only engines.
        providers={p['id']:p['name'] for p in Plugins(self.library).installed() if p['config'].get('enabled') and 'search' in p['capabilities']}
        selected=self.library.setting('numbered_fallbacks:'+kind,[]); self.fallbacks.clear()
        for key in dict.fromkeys([*selected,*providers]):
            item=QListWidgetItem(providers.get(key,key+'（当前不可用）')); item.setData(Qt.ItemDataRole.UserRole,key)
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked); self.fallbacks.addItem(item)
        self.primary.setEnabled(kind in FILMS); self.fallbacks.setEnabled(kind in FILMS); self.destination.setEnabled(kind in FILMS)
        self.destination.setText(rule.get('destination',''))
        naming=self.library.setting(rule_key(kind),{}); self.naming.folder.setText(naming.get('folder','')); self.naming.filename.setText(naming.get('filename',''))
        self.status.setText('该分类不自动刮削和整理；命名模板用于手动整理。' if kind not in FILMS else '识别存在歧义时进入任务中心待确认；整理将移动文件至上方目标。')
        self.loaded=self.signature();self.loaded_kind=kind
    def save(self):
        kind=self.kind.currentData(); destination=self.destination.text().strip()
        fallbacks=[self.fallbacks.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.fallbacks.count()) if self.fallbacks.item(i).checkState()==Qt.CheckState.Checked]
        try:
            naming=self.naming.value()
            if len(fallbacks)>7:raise ValueError('最多设置 7 个备用来源。')
            if kind in FILMS and fallbacks and not self.primary.currentData():raise ValueError('请先选择首选来源，或取消备用来源。')
            if destination and not Path(destination).is_absolute():raise ValueError('整理目标须为完整目录路径。')
        except ValueError as error:self.status.setText(str(error));return
        old=self.library.setting('partition:'+kind,{})
        new={**old,'plugin':self.primary.currentData() or '', 'destination':destination} if kind in FILMS else old
        if kind in FILMS and destination and new!=old:
            if QMessageBox.question(self,'保存自动整理规则','新入库文件会在识别完成后移动到：\n'+destination+'\n已有文件不会立即移动。是否保存？')!=QMessageBox.StandardButton.Yes:return
        values={rule_key(kind):naming}
        if kind in FILMS:values.update({'partition:'+kind:new,'numbered_fallbacks:'+kind:[p for p in fallbacks if p!=new['plugin']]})
        write_settings(self.library,values);self.loaded=self.signature();self.status.setText('已保存 '+KINDS[kind]+' 的分类默认规则。')
        if self.changed:self.changed()


class DirectoryRuleDialog(QDialog):
    """Review one source directory and stage its overrides without changing defaults."""
    def __init__(self,window,entry,pending=None,parent=None):
        super().__init__(parent or window);self.window=window;self.library=window.library;self.entry=copy.deepcopy(entry);self.pending=pending or {};self.naming_update={}
        self.setWindowTitle('目录详情与自动入库规则');self.resize(720,640)
        outer=QVBoxLayout(self);content=scroll_form(outer)
        content.addWidget(note(KINDS.get(entry['kind'],entry['kind'])+' · 监听源目录\n'+entry['path']))
        self.enabled=QCheckBox('启用自动监听（应用运行期间）');self.enabled.setChecked(entry.get('enabled',True));content.addWidget(self.enabled)
        form=QFormLayout();content.addLayout(form)
        self.plugin=QComboBox();self.plugin.setObjectName('directoryPrimary');add_provider_items(self.plugin,self.library,entry.get('plugin'),True,kind=entry.get('kind'));form.addRow('首选来源',self.plugin)
        self.inherit=QCheckBox('继承分类默认整理目标');self.inherit.setChecked('destination' not in entry);content.addWidget(self.inherit)
        row=QHBoxLayout();self.target=QLineEdit(entry.get('destination',''));self.target.setObjectName('directoryDestination');self.target.setPlaceholderText('留空保留原位置');row.addWidget(self.target)
        self.browse=QPushButton('选择目标…');row.addWidget(self.browse);content.addLayout(row)
        def choose():
            from .dialogs import existing_directory
            path=existing_directory(self,'选择此目录的整理目标',self.target.text())
            if path:self.target.setText(path)
        self.browse.clicked.connect(choose)
        self.summary=note('');self.summary.setObjectName('effectiveDirectoryRule');content.addWidget(self.summary)
        defaults=QPushButton('编辑分类默认来源、备用顺序与模板…');content.addWidget(defaults)
        defaults.clicked.connect(self.defaults)
        self.custom_naming=QCheckBox('为整理目标保存专用命名模板（使用同一目标的目录共用）');content.addWidget(self.custom_naming)
        from .organize_ui import RuleFields
        self.naming=RuleFields(content,{})
        content.addWidget(note('目录设置和目标模板暂存于本窗口。返回后点击“保存目录设置”才会生效；分类默认规则另行保存。'))
        self.status=note('');content.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('应用到目录草稿');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
        self.plugin.currentIndexChanged.connect(lambda:self.update_summary(False));self.inherit.toggled.connect(self.update_summary);self.target.editingFinished.connect(self.update_summary)
        self._naming_scope=None;self._naming_drafts={}
        self.custom_naming.toggled.connect(self.naming_enabled);self.update_summary()
    def draft(self):
        value=copy.deepcopy(self.entry);value['enabled']=self.enabled.isChecked()
        if self.plugin.currentData() is None:value.pop('plugin',None)
        else:value['plugin']=self.plugin.currentData()
        if self.inherit.isChecked():value.pop('destination',None)
        else:value['destination']=self.target.text().strip()
        return value
    def update_summary(self,*args):
        enabled=self.entry['kind'] in FILMS
        self.plugin.setEnabled(enabled);self.inherit.setEnabled(enabled);self.target.setEnabled(enabled and not self.inherit.isChecked());self.browse.setEnabled(self.target.isEnabled())
        rule=effective_directory_rule(self.library,self.draft(),self.pending)
        self.summary.setText(describe_directory_rule(self.library,self.draft(),self.pending))
        scope=rule['naming_key'] or rule_key(rule['kind'])
        if scope!=self._naming_scope:
            if self._naming_scope is not None:
                self._naming_drafts[self._naming_scope]=(self.custom_naming.isChecked(),self.naming.folder.text(),self.naming.filename.text())
            custom,folder,filename=self._naming_drafts.get(scope,(bool(rule['destination']) and not rule['naming_inherited'],rule['naming'].get('folder',''),rule['naming'].get('filename','')))
            self.custom_naming.setChecked(custom);self.naming.folder.setText(folder);self.naming.filename.setText(filename);self._naming_scope=scope
        self.custom_naming.setEnabled(bool(rule['destination']));self.naming_enabled()
    def naming_enabled(self,*args):
        enabled=self.custom_naming.isEnabled() and self.custom_naming.isChecked()
        self.naming.folder.setEnabled(enabled);self.naming.filename.setEnabled(enabled)
    def defaults(self):
        dialog=QDialog(self);dialog.setWindowTitle('分类默认规则');dialog.resize(720,650)
        layout=QVBoxLayout(dialog);editor=CategoryRules(self.window,allow_sources=False);editor.kind.setCurrentIndex(editor.kind.findData(self.entry['kind']));layout.addWidget(editor)
        close=QPushButton('返回目录详情');close.clicked.connect(dialog.accept);layout.addWidget(close);dialog.exec();self.update_summary()
    def save(self):
        entry=self.draft();destination=effective_directory_rule(self.library,entry)['destination']
        try:
            if destination and not Path(destination).is_absolute():raise ValueError('整理目标须为完整目录路径。')
            if destination:
                key=rule_key(entry['kind'],destination)
                self.naming_update={key:self.naming.value() if self.custom_naming.isChecked() else None}
        except ValueError as error:self.status.setText(str(error));return
        self.entry=entry;self.accept()


class MediaManagement(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setWindowTitle('媒体管理');self.resize(980,720)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);self._allow_close=False
        outer=QVBoxLayout(self);self.tabs=QTabWidget();outer.addWidget(self.tabs)
        from .library_tools_ui import LibraryTools
        self.directories=LibraryTools(window,embedded=True)
        directory_scroll=QScrollArea();directory_scroll.setWidgetResizable(True);directory_scroll.setFrameShape(QScrollArea.Shape.NoFrame);directory_scroll.setWidget(self.directories)
        self.tabs.addTab(directory_scroll,'目录与入库')
        self.rules=CategoryRules(window,lambda:self.directories.selection_changed());self.tabs.addTab(self.rules,'分类规则与来源')
        repair=self.page('检查文件与路径只生成报告；资料修复可补充缺失字段，也可强制覆盖展示资料与图片，保留个人评分、喜欢／收藏和播放记录。')
        self.action(repair,'资料修复与强制更新…',window.metadata_health)
        self.action(repair,'文件与路径体检报告…',self.audit)
        self.action(repair,'从本地 NFO 补充图片…',window.import_nfo_artwork)
        self.tabs.addTab(repair._scroll,'资料修复')
        organize=self.page('重复候选用于核对，不自动删除。当前影片的整理预览和默认播放版本在影片详情中操作。')
        self.action(organize,'重复候选与版本对比…',window.duplicate_versions)
        self.action(organize,'分类默认命名模板…',lambda:self.select('sources'))
        self.action(organize,'查看目录的整理目标与专用模板…',lambda:self.select('directories'))
        self.tabs.addTab(organize._scroll,'整理与版本')
        exports=self.page('导入和导出均先核对范围。导出按分类明确选择，当前影片或已选影片的导出入口在对应页面。')
        self.action(exports,'添加媒体文件夹…',window.import_dialog)
        self.export_kind=QComboBox();self.export_kind.addItem('所有本地电影、电视剧与 VR','')
        for key in ['movie','series','vr']:self.export_kind.addItem(KINDS[key],key)
        exports.layout().insertWidget(exports.layout().count()-1,self.export_kind)
        self.action(exports,'选择分类并预览 NFO 导出…',self.export_nfo)
        self.tabs.addTab(exports._scroll,'导入导出')
        close=QPushButton('关闭');close.clicked.connect(self.close);outer.addWidget(close)
    def page(self,text):
        container=QScrollArea();container.setWidgetResizable(True);container.setFrameShape(QScrollArea.Shape.NoFrame)
        body=QWidget();layout=QVBoxLayout(body);layout.addWidget(note(text));layout.addStretch();container.setWidget(body);body._scroll=container
        return body
    def action(self,page,title,callback):
        control=QPushButton(title);control.setMinimumHeight(42);control.clicked.connect(lambda checked=False:callback());page.layout().insertWidget(page.layout().count()-1,control)
    def audit(self):
        from .library_tools_ui import LibraryTools
        dialog=LibraryTools(self.window);dialog.tabs.setCurrentIndex(1);dialog.exec()
    def export_nfo(self):
        from .nfo_export_ui import export_dialog
        kind=self.export_kind.currentData();kinds=[kind] if kind else ['movie','series','vr']
        placeholders=','.join('?' for _ in kinds)
        ids=[row[0] for row in self.window.library.db.execute('SELECT DISTINCT w.id FROM works w JOIN files f ON f.work_id=w.id WHERE w.kind IN ('+placeholders+')',kinds)]
        if not ids:QMessageBox.information(self,'导出资料','所选分类没有本地影片。');return
        export_dialog(self.window,ids)
    def confirm_discard(self):
        if not (self.directories.has_changes() or self.rules.has_changes()):return True
        return QMessageBox.question(self,'未保存的媒体管理设置','目录或分类规则尚未保存。是否放弃更改并关闭？',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
    def reject(self):
        if self._allow_close or self.confirm_discard():super().reject()
    def closeEvent(self,event):
        if self.confirm_discard():
            self._allow_close=True
            try:super().closeEvent(event)
            finally:self._allow_close=False
        else:event.ignore()
    def select(self,section=None):
        index={'directories':0,'sources':1,'repair':2,'organize':3,'export':4}.get(section,0);self.tabs.setCurrentIndex(index)
        if index==0:self.directories.selection_changed()


def show_media_management(window,section=None):
    dialog=getattr(window,'media_management_dialog',None)
    if dialog is None:
        dialog=MediaManagement(window);window.media_management_dialog=dialog
        dialog.finished.connect(lambda _:setattr(window,'media_management_dialog',None))
    dialog.select(section);dialog.show();dialog.raise_();dialog.activateWindow();return dialog
