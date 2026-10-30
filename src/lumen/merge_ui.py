"""Searchable selection for explicit catalog merges."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QDialogButtonBox,QMessageBox,QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,QAbstractItemView
from PySide6.QtCore import QSize


def filter_choices(choices, text):
    tokens=text.casefold().split()
    count=0
    for index in range(choices.count()):
        item=choices.item(index)
        haystack=(item.data(Qt.ItemDataRole.UserRole+1) or item.text()).casefold()
        hidden=not all(token in haystack for token in tokens)
        item.setHidden(hidden)
        if not hidden:count+=1
    current=choices.currentItem()
    if current and current.isHidden():choices.setCurrentRow(-1)
    return count


class MergePicker(QDialog):
    def __init__(self, records, parent=None):
        super().__init__(parent);self.setWindowTitle('搜索并选择要合并的作品');self.resize(700,520)
        layout=QVBoxLayout(self)
        note=QLabel('选中的作品将并入当前作品。请核对名称、年份和文件路径。');note.setWordWrap(True);layout.addWidget(note)
        self.search=QLineEdit();self.search.setObjectName('mergeSearch');self.search.setPlaceholderText('搜索名称、作品编号、来源编号或文件路径；空格分隔多个关键词');layout.addWidget(self.search)
        self.items=QListWidget();self.items.setObjectName('mergeChoices');layout.addWidget(self.items)
        for work in records:
            paths=[file['path'] for file in work['files']]
            paths.extend(work['metadata'].get('fans_roots',[]))
            title=f"#{work['id']} · {work['title']} ({work['year'] or '未知年份'}) · {len(work['files'])} 个文件"
            item=QListWidgetItem(title+('\n'+paths[0] if paths else '\n尚未入库'))
            item.setData(Qt.ItemDataRole.UserRole,work['id'])
            item.setData(Qt.ItemDataRole.UserRole+1,' '.join([title,*paths,*work['metadata'].get('aliases',[]),*[str(source['source_id']) for source in work['sources']]]))
            item.setToolTip('\n'.join(paths));self.items.addItem(item)
        self.status=QLabel();layout.addWidget(self.status)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('选择此作品')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.search.textChanged.connect(self.filter)
        self.items.currentRowChanged.connect(self.update_selection)
        self.filter('');self.search.setFocus()

    def filter(self,text):
        count=filter_choices(self.items,text)
        self.status.setText(f'匹配 {count} / {self.items.count()} 部作品' if count else '没有匹配的作品，请调整搜索条件')
        self.update_selection()

    def update_selection(self,*_):
        item=self.items.currentItem()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(item is not None and not item.isHidden())

    def selected_id(self):
        item=self.items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item and not item.isHidden() else None


def merge_catalog_work(detail):
    from .background import run_background
    from .core import Library
    window=detail.window;target_id=detail.work_id;kind=detail.work['kind']
    def read(job):
        library=Library(window.library.directory,initialize=False)
        try:return [work for work in library.query({'kinds':[kind],'local':False}) if work['id']!=target_id]
        finally:library.close()
    def ready(records):
        if window._closing or window.detail_page is not detail:return
        if not records:
            QMessageBox.information(window,'合并作品','没有其他相同类型的作品可合并。');return
        picker=MergePicker(records,window)
        accepted=picker.exec();source_id=picker.selected_id();picker.deleteLater()
        if not accepted or source_id is None:return
        preview_and_merge(detail,[source_id])
    window.status.setText('正在后台读取可合并作品…')
    return run_background(window,read,ready,lambda error:window.status.setText('读取可合并作品失败：'+error))


class MergePreview(QDialog):
    def __init__(self,preview,parent=None):
        super().__init__(parent);self.setWindowTitle('合并预览');self.resize(940,740)
        layout=QVBoxLayout(self);self.preview=preview
        originals=preview['originals'];target=originals[0];result=preview['result'];sources=originals[1:]
        note=QLabel(f"将 {len(sources)} 个条目并入「{target['title']}」；确认后保存撤销记录，原始视频文件保留。");note.setWordWrap(True);layout.addWidget(note)
        def text(work,field):
            if field=='files':return str(len(work['files']))
            if field=='sources':return '、'.join(source['site']+':'+source['source_id'] for source in work['sources']) or '无'
            if field=='locked':return '、'.join(work['locked']) or '无'
            if field=='personal':return f"收藏 {'是' if work['favorite'] else '否'} / 想看 {'是' if work['watchlist'] else '否'} / 不感兴趣 {'是' if work['disliked'] else '否'}"
            if field=='thumbnail':return work.get('thumbnail') or '无'
            if field in {'actors','tags'}:
                values=work['metadata'].get(field,[]);return '、'.join(value['name'] if isinstance(value,dict) else str(value) for value in values) or '无'
            if field=='overview':return work['metadata'].get('overview') or '无'
            value=work.get(field);return str(value) if value is not None else '无'
        fields=[('标题','title'),('年份','year'),('个人评分','rating'),('个人状态','personal'),('文件数','files'),('来源','sources'),('演员','actors'),('标签','tags'),('简介','overview'),('海报路径','thumbnail'),('锁定字段','locked')]
        self.table=QTableWidget(len(fields),4);self.table.setObjectName('mergePreviewTable');self.table.setHorizontalHeaderLabels(['项目','当前作品','待并入条目','合并后'])
        self.table.setWordWrap(False)
        self.table.setStyleSheet('QTableCornerButton::section { background: #252525; border: none; }')
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row,(label,field) in enumerate(fields):
            values=[label,text(target,field),'\n'.join(f"#{work['id']} {text(work,field)}" for work in sources),text(result,field)]
            for column,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(value);self.table.setItem(row,column,item)
        layout.addWidget(self.table,1)
        art=preview['before']['artwork'].get(str(target['id'])) or {}
        self.cover_paths=[art.get('poster') or target.get('thumbnail'),art.get('poster') or result.get('thumbnail')]
        self.covers=[];covers=QHBoxLayout();layout.addLayout(covers)
        for title in ['当前海报','合并后海报']:
            column=QVBoxLayout();column.addWidget(QLabel(title));image=QLabel('无海报');image.setFixedSize(84,126);image.setAlignment(Qt.AlignmentFlag.AlignCenter);column.addWidget(image);covers.addLayout(column);self.covers.append(image)
        paths=QPlainTextEdit();paths.setReadOnly(True);paths.setMaximumHeight(100)
        paths.setPlainText('\n'.join(f"#{work['id']} {work['title']}\n"+'\n'.join(file['path'] for file in work['files']) for work in originals));layout.addWidget(paths)
        warning=QLabel('当前作品资料和评分优先；缺失值按现有合并规则补充。文件 ID、观看进度与书签保留。撤销仅恢复相关条目；后续资料或归属变化时会阻止覆盖。');warning.setWordWrap(True);layout.addWidget(warning)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('确认合并并保存撤销记录');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        from .images import image_cache
        image_cache().changed.connect(self.render_covers);self.render_covers()

    def render_covers(self):
        from .images import image_cache
        for label,path in zip(self.covers,self.cover_paths):
            if not path:continue
            image=image_cache().request(path,QSize(168,252))
            if not image.isNull():label.setPixmap(image.scaled(label.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))


def preview_and_merge(detail,source_ids,creator=None):
    from .background import run_background
    from .core import Library
    from .merge_history import preview_merge,apply_merge
    window=detail.window;target_id=detail.work_id
    def read(job):
        library=Library(window.library.directory,initialize=False)
        try:return preview_merge(library,source_ids,target_id,creator)
        finally:library.close()
    def ready(preview):
        if window._closing or window.detail_page is not detail:return
        dialog=MergePreview(preview,window);accepted=dialog.exec();dialog.deleteLater()
        if not accepted:return
        window.run_job('合并条目并保存撤销记录',lambda library,progress:apply_merge(library,preview),lambda _:refresh_after_merge(window,target_id))
    return run_background(window,read,ready,lambda error:QMessageBox.warning(window,'无法预览合并',str(error)))


def refresh_after_merge(window,target_id):
    player=window.player
    if player.file:
        row=window.library.db.execute('SELECT work_id FROM files WHERE id=?',(player.file['id'],)).fetchone()
        if row:
            player.file['work_id']=row['work_id']
            player.update_like(window.library.work(row['work_id']))
    window.reload_details(target_id)


def show_merge_history(detail):
    from .background import run_background
    from .core import Library
    from .merge_history import records,undo_merge
    window=detail.window;target_id=detail.work_id
    def read(job):
        library=Library(window.library.directory,initialize=False)
        try:return records(library,target_id)
        finally:library.close()
    def ready(history):
        if window._closing or window.detail_page is not detail:return
        dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.setWindowTitle('合并记录 / 撤销');dialog.resize(680,430)
        layout=QVBoxLayout(dialog);note=QLabel('选择合并记录撤销；合并后的观看进度保留，已修改的资料或文件归属不会被覆盖。');note.setWordWrap(True);layout.addWidget(note)
        choices=QListWidget();layout.addWidget(choices)
        for record in history:
            item=QListWidgetItem(record['created']+' · '+'、'.join(record['titles'])+(' · 已撤销' if record['status']=='undone' else ' · 可尝试撤销'));item.setData(Qt.ItemDataRole.UserRole,record);choices.addItem(item)
        if not history:layout.addWidget(QLabel('暂无手动合并记录；旧版合并与自动归集没有撤销快照。'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Close);undo=buttons.button(QDialogButtonBox.StandardButton.Ok);undo.setText('撤销选中合并');undo.setEnabled(False);buttons.button(QDialogButtonBox.StandardButton.Close).setText('关闭');layout.addWidget(buttons);buttons.rejected.connect(dialog.close)
        choices.currentRowChanged.connect(lambda _:undo.setEnabled(choices.currentItem() is not None and choices.currentItem().data(Qt.ItemDataRole.UserRole)['status']=='merged'))
        def apply():
            item=choices.currentItem()
            if item is None:return
            record=item.data(Qt.ItemDataRole.UserRole)
            if QMessageBox.question(window,'确认撤销','恢复合并前的作品、资料和文件归属？合并后新增的观看进度会保留。')!=QMessageBox.StandardButton.Yes:return
            dialog.close();window.run_job('撤销合并',lambda library,progress:undo_merge(library,record['id']),lambda _:refresh_after_merge(window,target_id))
        buttons.accepted.connect(apply);dialog.open()
    return run_background(window,read,ready,lambda error:window.status.setText('读取合并记录失败：'+str(error)))
