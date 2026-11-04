"""Naming-rule editor and paged, read-only organization preview."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QLabel, QPushButton, QCheckBox, QDialogButtonBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,QScrollArea,QWidget)
from .organize_templates import validate_rule, load_rule, save_rule, rule_key
from .files import plan_move, execute_move


HELP = ('字段：{code} 编号、{title} 标题、{year} 年份、{year_suffix} 带括号年份、'
        '{stem} 原文件名、{part} 分段、{season} 季、{episode} 集、{version} 版本序号。\n'
        '目录可用 / 分层。文件名不含扩展名；字幕语言后缀会保留。留空使用原有整理规则。')


class RuleFields:
    def __init__(self, layout, rule):
        form = QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);layout.addLayout(form)
        self.folder = QLineEdit(rule.get('folder', '')); self.folder.setObjectName('folderTemplate')
        self.filename = QLineEdit(rule.get('filename', '')); self.filename.setObjectName('filenameTemplate')
        self.folder.setPlaceholderText('例：{code} - {title}；留空使用标题（年份）')
        self.filename.setPlaceholderText('例：{code}；留空保留原文件名')
        form.addRow('目录模板', self.folder); form.addRow('文件名模板', self.filename)
        note = QLabel(HELP); note.setWordWrap(True); layout.addWidget(note)
    def value(self):
        return validate_rule({'folder': self.folder.text(), 'filename': self.filename.text()})


def show_naming_rules(window, kind='movie', path=None):
    dialog = QDialog(window); dialog.setWindowTitle('整理命名规则'); dialog.resize(700, 350)
    layout = QVBoxLayout(dialog)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body=QWidget();content=QVBoxLayout(body);scroll.setWidget(body);layout.addWidget(scroll,1)
    scope = QLabel('目标目录规则 · 所有整理到此目录的作品共用' if path else '分类默认规则：' + {'movie':'电影','series':'电视剧','vr':'VR电影','fans':'Fans','other':'其他视频'}.get(kind, kind))
    scope.setObjectName('namingRuleScope');scope.setWordWrap(True);content.addWidget(scope)
    if path:
        directory=QLineEdit(str(Path(path).resolve()));directory.setReadOnly(True);directory.setToolTip(directory.text());content.addWidget(directory)
    rule = window.library.setting(rule_key(kind, path), {'folder':'','filename':''})
    fields = RuleFields(content, rule)
    status = QLabel('保存后应用于后续整理；不会立即移动已有文件。'); status.setWordWrap(True); layout.addWidget(status)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
    buttons.rejected.connect(dialog.reject)
    def save():
        try: save_rule(window.library, kind, fields.value(), path)
        except ValueError as error: status.setText(str(error)); return
        dialog.accept()
    buttons.accepted.connect(save)
    if path:
        inherit = QPushButton('恢复使用分类默认规则');content.addWidget(inherit)
        def reset():
            with window.library.db: window.library.db.execute('DELETE FROM settings WHERE key=?', (rule_key(kind, path),))
            dialog.accept()
        inherit.clicked.connect(reset)
    layout.addWidget(buttons)
    result = dialog.exec(); dialog.deleteLater(); return result


class Organizer(QDialog):
    def __init__(self, window, work_id):
        super().__init__(window); self.window = window; self.work_id = work_id
        self.setWindowTitle('整理命名与预览'); self.resize(1000, 700)
        self.work = window.library.work(work_id); self.plan = None; self.page = 0; self.generation = 0; self.closed = False
        layout = QVBoxLayout(self)
        scope=QLabel('当前影片：'+self.work['title']);scope.setWordWrap(True);scope.setToolTip(self.work['title']);scope.setMaximumHeight(48);layout.addWidget(scope)
        settings=QScrollArea();settings.setObjectName('organizerSettings');settings.setWidgetResizable(True);settings.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);settings.setMinimumHeight(120);settings.setMaximumHeight(280)
        body=QWidget();content=QVBoxLayout(body);settings.setWidget(body);layout.addWidget(settings)
        self.target = QLineEdit(window.library.setting('partition:' + self.work['kind'], {}).get('destination', ''))
        self.target.setObjectName('organizeTarget'); self.target.setPlaceholderText('选择整理目标根目录')
        row = QHBoxLayout(); row.addWidget(self.target)
        choose = QPushButton('选择目标…'); row.addWidget(choose); content.addLayout(row)
        def browse():
            from .dialogs import existing_directory
            path = existing_directory(self, '选择整理目标根目录', self.target.text())
            if path: self.target.setText(path); self.reload_rule()
        choose.clicked.connect(browse)
        initial = load_rule(window.library, self.work['kind'], self.target.text()) if self.target.text() else window.library.setting(rule_key(self.work['kind']), {'folder':'','filename':''})
        self.fields = RuleFields(content, initial)
        reload = QPushButton('读取目标目录 / 分类默认规则'); reload.clicked.connect(self.reload_rule); content.addWidget(reload)
        self.remember = QCheckBox('保存为目标目录的共用模板');self.remember.setToolTip('此后的作品整理到同一个目标目录时，也会使用这份模板。');content.addWidget(self.remember)
        self.status = QLabel('先预览，核对全部文件的新路径，再确认执行。原文件会在复制校验成功后删除。'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.table = QTableWidget(0, 2); self.table.setHorizontalHeaderLabels(['原路径', '目标路径'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.table.setWordWrap(False)
        self.table.setMinimumHeight(120);layout.addWidget(self.table,1)
        pages = QHBoxLayout(); self.previous = QPushButton('上一页'); self.next = QPushButton('下一页')
        self.page_label = QLabel(); pages.addWidget(self.previous); pages.addWidget(self.page_label); pages.addWidget(self.next); layout.addLayout(pages)
        self.previous.clicked.connect(lambda: self.turn(-1)); self.next.clicked.connect(lambda: self.turn(1))
        actions = QHBoxLayout(); self.preview = QPushButton('生成预览'); self.execute = QPushButton('确认并执行'); close = QPushButton('关闭')
        self.preview.setObjectName('previewOrganization'); self.execute.setObjectName('executeOrganization')
        self.execute.setProperty('primaryAction',True)
        actions.addWidget(self.preview); actions.addWidget(self.execute); actions.addWidget(close); layout.addLayout(actions)
        self.preview.clicked.connect(self.build); self.execute.clicked.connect(self.apply); close.clicked.connect(self.reject)
        for field in (self.target, self.fields.folder, self.fields.filename): field.textChanged.connect(self.invalidate)
        def finished(_): self.closed = True; self.invalidate()
        self.finished.connect(finished); self.invalidate()
    def invalidate(self, *_):
        self.generation += 1; self.plan = None; self.execute.setEnabled(False); self.table.setRowCount(0)
        self.page_label.setText('尚未生成预览'); self.previous.setEnabled(False); self.next.setEnabled(False)
    def reload_rule(self):
        if not self.target.text().strip(): return
        try: rule = load_rule(self.window.library, self.work['kind'], self.target.text().strip())
        except ValueError as error: self.status.setText(str(error)); return
        self.fields.folder.setText(rule['folder']); self.fields.filename.setText(rule['filename'])
    def build(self):
        target = self.target.text().strip()
        if not target: self.status.setText('请选择整理目标目录。'); return
        try: rule = self.fields.value()
        except ValueError as error: self.status.setText(str(error)); return
        self.invalidate(); generation = self.generation; work_id = self.work_id
        self.status.setText('正在后台检查目标路径并校验源文件，尚未移动文件…')
        def prepare(lib, progress):
            try: return {'plan': plan_move(lib, work_id, target, rule=rule,cancelled=getattr(progress,'cancelled',None))}
            except (ValueError, OSError) as error: return {'error': str(error)}
        def ready(result):
            if self.closed or generation != self.generation or not self.isVisible(): return
            if result.get('error'): self.status.setText('无法整理：' + result['error']); return
            self.plan = result['plan']; self.page = 0; self.render()
            self.status.setText(f'共 {len(self.plan)} 个文件；请核对目标路径。' if self.plan else '文件已经符合当前目录和命名规则，无需移动。')
            self.execute.setEnabled(bool(self.plan))
        self.window.run_job('检查整理命名计划', prepare, ready)
    def render(self):
        items = (self.plan or [])[self.page*100:(self.page+1)*100]; self.table.setRowCount(len(items))
        for index, pair in enumerate(items):
            for column, key in enumerate(('source','target')):
                item = QTableWidgetItem(pair[key]); item.setToolTip(pair[key]); self.table.setItem(index,column,item)
        total = len(self.plan or [])
        self.page_label.setText(f'第 {self.page+1} 页 · 共 {total} 个文件，每页 100 个')
        self.previous.setEnabled(self.page>0); self.next.setEnabled((self.page+1)*100<total)
    def turn(self, direction):
        self.page = max(0, self.page + direction); self.render()
    def apply(self):
        if not self.plan: return
        plan = self.plan; work_id = self.work_id
        if self.remember.isChecked():
            try: save_rule(self.window.library, self.work['kind'], self.fields.value(), self.target.text().strip())
            except ValueError as error: self.status.setText(str(error)); return
        window=self.window
        self.accept()
        window.run_job('按预览整理文件', lambda lib,p:execute_move(lib,plan,cancelled=getattr(p,'cancelled',None)), lambda _:window.reload_details(work_id))


def show_organizer(details):
    window = details.window
    existing = getattr(window, 'organizer_dialog', None)
    if existing is not None:
        existing.show(); existing.raise_(); existing.activateWindow(); return existing
    dialog = Organizer(window, details.work_id); window.organizer_dialog = dialog
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.finished.connect(lambda _:setattr(window,'organizer_dialog',None))
    dialog.show(); return dialog
