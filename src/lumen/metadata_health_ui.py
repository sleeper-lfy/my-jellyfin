"""A background-driven panel for missing fields and failed image caches."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
    QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QPlainTextEdit)
from .metadata_health import scan_health,repair_many,LABELS
from .plugins import Plugins
from .core import ImportCancelled


def show_metadata_health(window):
    existing=getattr(window,'metadata_health_dialog',None)
    if existing is not None:existing.show();existing.raise_();existing.activateWindow();return existing
    dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.metadata_health_dialog=dialog
    dialog.destroyed.connect(lambda:setattr(window,'metadata_health_dialog',None) if window.metadata_health_dialog is dialog else None)
    dialog.setWindowTitle('资料缺失与图片修复');dialog.resize(900,650)
    layout=QVBoxLayout(dialog)
    note=QLabel('只补充缺失资料与图片，保留现有内容、NFO 和锁定字段。选择表格中的影片可缩小处理范围。');note.setWordWrap(True);layout.addWidget(note)
    toolbar=QHBoxLayout();layout.addLayout(toolbar)
    scope=QComboBox();scope.setObjectName('healthScope');scope.addItem('全部本地影片','')
    for title,kind in [('电影','movie'),('电视剧','series'),('VR 电影','vr')]:scope.addItem(title,kind)
    scope.setCurrentIndex(max(0,scope.findData(window.section)))
    source=QComboBox();source.setObjectName('healthSource');source.addItem('已有来源 / 分类默认及备用来源',None)
    for plugin in Plugins(window.library).installed():
        if plugin['config'].get('enabled') and set(plugin['capabilities'])&{'search','detail'}:source.addItem(plugin['name'],[plugin['id']])
    toolbar.addWidget(scope);toolbar.addWidget(source,1)
    scan=QPushButton('重新检查');scan.setObjectName('scanMetadataHealth');toolbar.addWidget(scan)
    table=QTableWidget(0,5);table.setObjectName('metadataHealthTable')
    table.setHorizontalHeaderLabels(['影片','缺失资料','待补图片','受保护字段','已有来源'])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setWordWrap(False);table.setTextElideMode(Qt.TextElideMode.ElideRight)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.setColumnWidth(0,220);table.setColumnWidth(1,180);table.setColumnWidth(2,90);table.setColumnWidth(3,130)
    table.horizontalHeader().setStretchLastSection(True);layout.addWidget(table,1)
    status=QLabel('准备检查…');status.setWordWrap(True);layout.addWidget(status)
    target_label=QLabel('');target_label.setObjectName('metadataRepairScope');target_label.setWordWrap(True);layout.addWidget(target_label)
    actions=QHBoxLayout();layout.addLayout(actions)
    fill=QPushButton('补全全部');fill.setObjectName('repairMissingMetadata');fill.setProperty('primaryAction',True)
    images=QPushButton('仅重试缺失图片');images.setObjectName('retryMissingImages')
    actions.addWidget(fill);actions.addWidget(images)
    report=QPlainTextEdit();report.setReadOnly(True);report.setMaximumHeight(120);report.setPlaceholderText('修复结果与未完成原因会显示在这里；完整结果保存在任务记录中。');report.hide();layout.addWidget(report)
    rows=[];all_rows=[];busy=[False]
    def alive():return getattr(window,'metadata_health_dialog',None) is dialog
    def set_busy(value):
        busy[0]=value
        if not alive():return
        for control in (scan,scope,source,fill,images):control.setEnabled(not value)
        table.setEnabled(not value)
        update_target()
    def update_target():
        if not alive():return
        count=len(table.selectionModel().selectedRows());total=count or len(rows)
        target='选中的' if count else '当前分类全部'
        target_label.setText(f'处理范围：{target} {total} 部影片'+('' if count else '（未选择单片）'))
        fill.setText(f'补全选中 {total} 部' if count else f'补全全部 {total} 部')
        images.setText(f'仅补图 · {total} 部')
        fill.setEnabled(total>0 and not busy[0]);images.setEnabled(total>0 and not busy[0])
    def render():
        kind=scope.currentData();rows[:]=[item for item in all_rows if not kind or item['kind']==kind]
        table.setRowCount(len(rows))
        for index,item in enumerate(rows):
            protected=list(item['locked'])
            if item['image_locked']:protected.append('images')
            values=[item['title'],'、'.join(LABELS[field] for field in item['missing']),str(item['images']),
                    '、'.join(LABELS[field] for field in protected),'、'.join(item['sources']) or '未关联']
            for column,value in enumerate(values):
                cell=QTableWidgetItem(value);cell.setToolTip(value);table.setItem(index,column,cell)
        status.setText(f'当前分类有 {len(rows)} 部影片存在缺失资料或图片。手工锁定或 NFO 保护的字段会保留。')
        update_target()
    def scanned(result):
        if not alive():return
        set_busy(False)
        if result.get('fatal'):status.setText(result['fatal']);return
        all_rows[:]=result['items'];render()
    def scan_now():
        if busy[0]:return
        set_busy(True);status.setText('正在后台检查本地影片资料…')
        def scan_job(library,p):
            try:return scan_health(library,progress=p,cancelled=p.cancelled)
            except ImportCancelled:return {'fatal':'检查已停止，可重新检查。'}
            except Exception as error:return {'fatal':'检查失败：'+str(error)}
        window.run_job('检查缺失影片资料',scan_job,scanned)
    def complete(result):
        if window.detail_page is not None:window.reload_details(window.detail_page.work_id)
        if not alive():return
        set_busy(False)
        if result.get('fatal'):status.setText(result['fatal']);return
        summary=f"已更新 {result['updated']} 部 · 补图 {result['images']} 张 · 有未完成项 {result['failed']} 部 · 未改动 {result['skipped']} 部"
        if result.get('stopped'):summary='已停止，已完成内容保留。'+summary
        lines=[summary]
        for item in result['items'][:500]:
            detail='补齐 '+ '、'.join(LABELS.get(field,field) for field in item['fields']) if item['fields'] else '无资料字段变更'
            detail+=f"；补图 {item['images']} 张"
            if item['errors']:detail+='；'+'；'.join(item['errors'])
            lines.append(item['title']+'：'+detail)
        report.setPlainText('\n'.join(lines));report.show();window.status.setText(summary);scan_now()
    def begin(images_only):
        if busy[0]:return
        selected=sorted({index.row() for index in table.selectionModel().selectedRows()})
        identifiers=[rows[index]['id'] for index in selected] if selected else [item['id'] for item in rows]
        if not identifiers:status.setText('当前没有待处理影片。');return
        providers=source.currentData();set_busy(True);status.setText('资料修复已加入后台队列…')
        def repair_job(library,p):
            try:return repair_many(library,identifiers,images_only=images_only,plugin_ids=providers,progress=p,cancelled=p.cancelled)
            except Exception as error:return {'fatal':'修复未完成：'+str(error)}
        window.run_job('重试缺失图片' if images_only else '补全缺失影片资料',repair_job,complete)
    scan.clicked.connect(scan_now);scope.currentIndexChanged.connect(render)
    table.itemSelectionChanged.connect(update_target)
    fill.clicked.connect(lambda:begin(False));images.clicked.connect(lambda:begin(True))
    dialog.show();scan_now();return dialog
