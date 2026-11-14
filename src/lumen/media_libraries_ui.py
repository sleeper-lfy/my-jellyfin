"""PC-only named library administration, using native directory pickers and existing jobs."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,
    QCheckBox,QSpinBox,QListWidget,QListWidgetItem,QPushButton,QLabel,QDialogButtonBox,QScrollArea,
    QPlainTextEdit,QMessageBox)
from . import media_libraries as libraries


def note(text):
    view=QLabel(text);view.setWordWrap(True);return view


class MediaLibraryDialog(QDialog):
    def __init__(self,window,item=None,parent=None):
        super().__init__(parent or window);self.window=window;self.library=window.library;self.item=item;self.saved=None
        self.setWindowTitle('编辑媒体库' if item else '添加媒体库');self.resize(760,740)
        outer=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();content=QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll,1)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);content.addLayout(form)
        self.name=QLineEdit(item['name'] if item else '');self.name.setObjectName('mediaLibraryName');form.addRow('媒体库名称',self.name)
        self.kind=QComboBox();self.kind.setObjectName('mediaLibraryKind')
        for key,label in libraries.KINDS.items():self.kind.addItem(label,key)
        if item:self.kind.setCurrentIndex(self.kind.findData(item['kind']));self.kind.setEnabled(False)
        form.addRow('媒体类型',self.kind)
        self.roots=QListWidget();self.roots.setObjectName('mediaLibraryRoots');self.roots.setMinimumHeight(110);self.roots.setMaximumHeight(180);content.addWidget(note('媒体目录（可添加多个；勾选的目录参与自动监听，未勾选仍可手动扫描）'));content.addWidget(self.roots)
        path_row=QHBoxLayout();self.path=QLineEdit();self.path.setObjectName('mediaLibraryPath');self.path.setPlaceholderText('粘贴完整目录路径');path_row.addWidget(self.path,1)
        for title,callback in [('选择目录…',self.choose_root),('添加路径',self.add_root),('移除选中目录',self.remove_root)]:
            button=QPushButton(title);button.clicked.connect(callback);path_row.addWidget(button)
        content.addLayout(path_row)
        self.watch=QCheckBox('启用本媒体库的目录监听');self.watch.setObjectName('mediaLibraryWatch');content.addWidget(self.watch)
        self.settle=QSpinBox();self.settle.setRange(5,600);self.settle.setSuffix(' 秒');form.addRow('文件稳定等待',self.settle)
        rules=QFormLayout();content.addLayout(rules);self.primary=QComboBox();self.primary.setObjectName('mediaLibraryPrimary');rules.addRow('首选刮削来源',self.primary)
        self.fallbacks=QListWidget();self.fallbacks.setObjectName('mediaLibraryFallbacks');self.fallbacks.setMaximumHeight(120);content.addWidget(note('备用来源：勾选后按从上到下顺序尝试；配置独立于同类型的其他媒体库。'));content.addWidget(self.fallbacks)
        controls=QHBoxLayout()
        for title,delta in [('上移',-1),('下移',1)]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,delta=delta:self.move_source(delta));controls.addWidget(button)
        content.addLayout(controls)
        self.destination=QLineEdit();self.destination.setObjectName('mediaLibraryDestination');self.destination.setPlaceholderText('留空保留原位置')
        row=QHBoxLayout();row.addWidget(self.destination,1);choose=QPushButton('选择整理目标…');choose.clicked.connect(self.choose_destination);row.addWidget(choose);content.addLayout(row)
        from .organize_ui import RuleFields
        config=item['config'] if item else {};self.naming=RuleFields(content,config.get('naming',{}))
        content.addWidget(note('来源和命名模板按媒体库保存，不继承后续全局变更。整理只处理本库文件；同一作品的资料、评分与收藏沿用现有共享规则。移除目录只停止监听，不删除已入库记录。'))
        self.scan_after=QCheckBox('保存后扫描此媒体库');self.scan_after.setChecked(item is None);content.addWidget(self.scan_after)
        self.status=note('');self.status.setObjectName('mediaLibraryValidation');outer.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
        self.watch.setChecked(config.get('watch',True));self.settle.setValue(config.get('settle_seconds',15));self.destination.setText(config.get('destination',''))
        for root in config.get('roots',[]):self.append_root(root['path'],root.get('enabled',True))
        self.load_sources(config);self.kind.currentIndexChanged.connect(lambda:self.load_sources({}))
    def append_root(self,path,enabled=True):
        row=QListWidgetItem(path);row.setData(Qt.ItemDataRole.UserRole,path);row.setFlags(row.flags()|Qt.ItemFlag.ItemIsUserCheckable);row.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked);self.roots.addItem(row)
    def add_root(self):
        try:path=libraries.normalized(self.path.text())
        except ValueError as error:self.status.setText(str(error));return
        if any(self.roots.item(i).data(Qt.ItemDataRole.UserRole)==path for i in range(self.roots.count())):self.status.setText('此目录已在列表中');return
        self.append_root(path);self.path.clear();self.status.clear()
    def choose_root(self):
        from .dialogs import existing_directory
        path=existing_directory(self,'选择媒体库目录',self.path.text())
        if path:self.path.setText(path);self.add_root()
    def remove_root(self):
        row=self.roots.currentRow()
        if row>=0:self.roots.takeItem(row)
    def choose_destination(self):
        from .dialogs import existing_directory
        path=existing_directory(self,'选择此媒体库的整理目标',self.destination.text())
        if path:self.destination.setText(path)
    def load_sources(self,config):
        from .media_management_ui import add_provider_items
        from .plugins import Plugins
        self.primary.clear();add_provider_items(self.primary,self.library,config.get('plugin',''),kind=self.kind.currentData())
        choices={p['id']:p['name'] for p in Plugins(self.library).installed() if p['config'].get('enabled') and 'search' in p['capabilities'] and (not p.get('media_kinds') or self.kind.currentData() in p['media_kinds'])}
        selected=config.get('fallback_plugins',[]);self.fallbacks.clear()
        for key in dict.fromkeys([*selected,*choices]):
            row=QListWidgetItem(choices.get(key,key+'（当前不可用）'));row.setData(Qt.ItemDataRole.UserRole,key);row.setFlags(row.flags()|Qt.ItemFlag.ItemIsUserCheckable);row.setCheckState(Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked);self.fallbacks.addItem(row)
        scrapable=self.kind.currentData() in {'movie','series','vr'}
        self.primary.setEnabled(scrapable);self.fallbacks.setEnabled(scrapable);self.destination.setEnabled(scrapable)
        if not scrapable:self.primary.setCurrentIndex(self.primary.findData(''));self.destination.clear()
    def move_source(self,delta):
        row=self.fallbacks.currentRow();target=row+delta
        if 0<=row<self.fallbacks.count() and 0<=target<self.fallbacks.count():self.fallbacks.insertItem(target,self.fallbacks.takeItem(row));self.fallbacks.setCurrentRow(target)
    def draft(self):
        return {'roots':[{'path':self.roots.item(i).data(Qt.ItemDataRole.UserRole),'enabled':self.roots.item(i).checkState()==Qt.CheckState.Checked} for i in range(self.roots.count())],
                'watch':self.watch.isChecked(),'settle_seconds':self.settle.value(),'plugin':self.primary.currentData() or '',
                'fallback_plugins':[self.fallbacks.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.fallbacks.count()) if self.fallbacks.item(i).checkState()==Qt.CheckState.Checked] if self.fallbacks.isEnabled() else [],
                'destination':self.destination.text().strip(),'naming':self.naming.value()}
    def save(self):
        try:
            config=self.draft();identifier=self.item['id'] if self.item else None
            libraries.validate(self.library,self.name.text(),self.kind.currentData(),config,identifier)
            if config['destination'] and (not self.item or config!=self.item['config']):
                if QMessageBox.question(self,'确认此媒体库的自动整理','后续扫描或监听入库的文件会按当前命名规则移动到：\n'+config['destination']+'\n保存规则本身不立即移动已有文件；是否保存？')!=QMessageBox.StandardButton.Yes:return
            self.saved=libraries.save(self.library,self.name.text(),self.kind.currentData(),config,identifier)
        except (ValueError,OSError) as error:self.status.setText(str(error));return
        self.accept()


class MediaLibrariesPanel(QWidget):
    def __init__(self,window,parent=None):
        super().__init__(parent);self.window=window;self.library=window.library
        outer=QVBoxLayout(self);outer.addWidget(note('自定义媒体库：一个类型、多个目录，各自保存刮削来源与整理规则。手机只浏览；配置在本机完成。'))
        self.list=QListWidget();self.list.setObjectName('managedMediaLibraries');outer.addWidget(self.list,1)
        actions=QHBoxLayout();outer.addLayout(actions)
        for title,callback in [('添加媒体库',self.add),('编辑选中库',self.edit),('扫描选中库',self.scan),('打开选中库',self.open),('移除选中库',self.remove)]:
            button=QPushButton(title);button.clicked.connect(callback);actions.addWidget(button)
        migrate=QPushButton('迁移原有监听目录与已入库媒体');migrate.setObjectName('migrateMediaLibraries');migrate.clicked.connect(self.migrate);outer.addWidget(migrate)
        self.report=QPlainTextEdit();self.report.setObjectName('mediaLibraryReport');self.report.setReadOnly(True);self.report.setMaximumHeight(170);outer.addWidget(self.report)
        self.list.currentRowChanged.connect(self.selected);self.list.itemDoubleClicked.connect(lambda _:self.edit());self.reload()
    def identifier(self):
        item=self.list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else None
    def reload(self,selected=None):
        current=selected or self.identifier();self.list.clear()
        for item in libraries.list_libraries(self.library):
            row=QListWidgetItem(item['name']+' · '+libraries.KINDS[item['kind']]+f" · {item['count']} 部 · {len(item['config']['roots'])} 个目录");row.setData(Qt.ItemDataRole.UserRole,item['id']);self.list.addItem(row)
            if item['id']==current:self.list.setCurrentItem(row)
        self.selected()
        if hasattr(self.window,'refresh_media_libraries'):self.window.refresh_media_libraries()
    def selected(self,*args):
        if self.identifier() is None:self.report.setPlainText('选择媒体库查看规则与最近扫描结果。');return
        item=libraries.get(self.library,self.identifier());cfg=item['config'];status=self.library.setting('media-library-scan:'+str(item['id']),{})
        self.report.setPlainText('\n'.join([item['name']+' · '+libraries.KINDS[item['kind']],'目录：'+('、'.join(r['path'] for r in cfg['roots']) or '未配置目录'),
            '首选来源：'+(cfg['plugin'] or '不自动刮削'),'备用顺序：'+(' → '.join(cfg['fallback_plugins']) or '无'),
            '整理目标：'+(cfg['destination'] or '保留原位置'),'命名模板：'+json.dumps(cfg['naming'],ensure_ascii=False),'最近扫描：'+json.dumps(status,ensure_ascii=False)]))
    def add(self):self.edit(True)
    def edit(self,new=False):
        identifier=None if new else self.identifier()
        if not new and identifier is None:return
        dialog=MediaLibraryDialog(self.window,libraries.get(self.library,identifier) if identifier else None,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.reload(dialog.saved['id'])
            if dialog.scan_after.isChecked():self.scan()
        dialog.deleteLater()
    def scan(self):
        identifier=self.identifier()
        if identifier is None:return
        if not libraries.get(self.library,identifier)['config']['roots']:self.report.setPlainText('此媒体库尚未配置目录，请先编辑。');return
        self.report.setPlainText('扫描已加入后台任务队列…')
        def done(result):
            self.reload(identifier);self.report.setPlainText('扫描完成：新增 '+str(result['imported'])+'，更新 '+str(result['updated'])+'，待稳定 '+str(result['waiting'])+'，缺失 '+str(len(result['missing']))+'，离线 '+str(len(result['offline']))+'，错误 '+str(len(result['errors']))+'。\n缺失文件仅报告，不自动删除记录。')
            self.window.refresh()
        self.window.run_job('扫描媒体库',lambda lib,p:libraries.scan(lib,identifier,p,p.cancelled),done)
    def open(self):
        if self.identifier() is not None:self.window.open_media_library(self.identifier())
    def remove(self):
        identifier=self.identifier()
        if identifier is None:return
        if QMessageBox.question(self,'移除媒体库','移除此媒体库的配置和归属？\n磁盘视频、已入库影片、评分、收藏与观看记录都会保留在“全部媒体”。')!=QMessageBox.StandardButton.Yes:return
        try:libraries.remove(self.library,identifier)
        except ValueError as error:self.report.setPlainText(str(error));return
        self.reload();self.window.refresh()
    def migrate(self):
        if QMessageBox.question(self,'迁移原有媒体配置','将类型和实际规则相同的旧监听目录合并到一个媒体库，不同规则分别保留。\n其他已入库文件按类型建立不监听的媒体库；不移动文件或改动个人状态。是否迁移？')!=QMessageBox.StandardButton.Yes:return
        try:created=libraries.migrate_legacy(self.library)
        except (ValueError,OSError) as error:self.report.setPlainText('迁移未完成，原配置保留：'+str(error));return
        self.reload();self.report.setPlainText('已迁移 '+str(len(created))+' 个媒体库；已有资料与个人状态保留。')
