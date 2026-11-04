"""Version comparison UI using background media inspection."""
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMessageBox,QListWidget,QMenu,QPlainTextEdit
from .versions import inspect_versions,set_preferred,duplicate_candidates


class VersionTable(QTableWidget):
    """Keep comparison fields visible even when names or probe errors are long."""
    def __init__(self):
        super().__init__(0,8)
        self.setObjectName('versionComparison')
        self.setWordWrap(False);self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setMinimumSectionSize(40)
        self.verticalHeader().hide()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        available=self.viewport().width()
        minimums=(160,44,64,52,66,64,64,84)
        extra=max(0,available-sum(minimums))
        weights=(.35,0,.08,.08,.07,.07,.10,.25)
        widths=[base+int(extra*weight) for base,weight in zip(minimums,weights)]
        widths[-1]+=max(0,available-sum(widths))
        for column,width in enumerate(widths):self.setColumnWidth(column,width)


def show_versions(window,work_ids):
    dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.setWindowTitle('版本对比与默认播放');dialog.resize(1100,620)
    layout=QVBoxLayout(dialog);status=QLabel('正在后台读取版本信息…');status.setWordWrap(True);layout.addWidget(status)
    table=VersionTable();table.setHorizontalHeaderLabels(['影片 / 文件','默认','分辨率','编码','大小','时长','音轨','字幕 / 状态'])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);layout.addWidget(table,1)
    detail=QPlainTextEdit();detail.setObjectName('versionSelectionDetails');detail.setReadOnly(True);detail.setMaximumHeight(92);detail.hide();layout.addWidget(detail)
    rows=[];closed=[False];dialog.finished.connect(lambda _:closed.__setitem__(0,True))
    def ready(records):
        if closed[0]:return
        rows[:]=records;table.setRowCount(len(rows))
        for index,row in enumerate(rows):
            values=[Path(row['path']).name,'默认' if row['default'] else '',row['resolution'],row['codec'],f"{row['size']/1048576:.1f} MiB" if row['size'] is not None else '离线',f"{row['duration']/60:.1f} 分钟",row['audio'],'读取失败' if row['error'] else row['subtitles'] or '无字幕']
            for column,value in enumerate(values):
                item=QTableWidgetItem(str(value));item.setToolTip(row['title']+'\n'+row['path'] if column==0 else row['error'] if column==7 and row['error'] else str(value));table.setItem(index,column,item)
        status.setText(f'共 {len(rows)} 个视频文件。默认版本只影响其所属电影 / VR；电视剧仍按季集播放。')
        update_selection()
    def load():window.run_job('读取视频版本',lambda lib,p:inspect_versions(lib,work_ids,p,p.cancelled),ready)
    def selected():
        index=table.currentRow();return rows[index] if 0<=index<len(rows) else None
    def update_selection():
        if closed[0]:return
        row=selected()
        for control in selected_controls:control.setEnabled(row is not None)
        detail.setVisible(row is not None)
        if row:
            detail.setPlainText(row['title']+'\n'+row['path']+'\n音轨：'+row['audio']+'；字幕：'+(row['subtitles'] or '无')+(('\n读取状态：'+row['error']) if row['error'] else ''))
    def prefer(clear=False):
        row=selected()
        if not row:return
        try:set_preferred(window.library,row['work_id'],None if clear else row['id'])
        except ValueError as error:QMessageBox.warning(dialog,'未设置',str(error));return
        for record in rows:
            if record['work_id']==row['work_id']:record['default']=not clear and record['id']==row['id']
        ready(list(rows))
    def locate():
        row=selected()
        if row:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(row['path']).parent)))
    def play():
        row=selected()
        if row:window.play_file(window.library.work(row['work_id'])['files'][next(i for i,f in enumerate(window.library.work(row['work_id'])['files']) if f['id']==row['id'])])
    def remove_record():
        row=selected()
        if not row:return
        if QMessageBox.question(dialog,'仅移出此版本',Path(row['path']).name+'\n将移除这个文件的媒体库记录及播放历史，磁盘文件保留。下次扫描可能重新入库。是否继续？')!=QMessageBox.StandardButton.Yes:return
        def remove(lib,p):
            current=next((file for file in lib.work(row['work_id'])['files'] if file['id']==row['id']),None)
            if not current or current['path']!=row['path']:raise ValueError('文件信息已变化，请重新读取')
            if lib.db.execute('SELECT 1 FROM sessions WHERE file_id=? AND ended IS NULL',(row['id'],)).fetchone():raise ValueError('请先停止此版本的播放')
            if lib.setting('preferred-file:'+str(row['work_id']))==row['id']:lib.set_setting('preferred-file:'+str(row['work_id']),None)
            return lib.remove_local_records(row['work_id'],[row['id']])
        def done(result):
            if closed[0]:return
            if result.get('removed_work'):
                dialog.close()
                if window.detail_page and window.detail_page.work_id==row['work_id']:window.back_details()
            else:load()
        window.run_job('移出选中版本记录',remove,done)
    controls=QHBoxLayout();layout.addLayout(controls)
    selected_controls=[]
    for label,action in [('播放选中版本',play),('设为默认版本',lambda:prefer())]:
        button=QPushButton(label);button.clicked.connect(action);controls.addWidget(button);selected_controls.append(button)
        if label=='播放选中版本':button.setObjectName('primary')
    more=QPushButton('版本操作');menu=QMenu(more);more.setMenu(menu);controls.addWidget(more);selected_controls.append(more)
    menu.addAction('恢复自动选择',lambda:prefer(True));menu.addAction('打开文件目录',locate)
    menu.addSeparator();menu.addAction('仅移出选中版本…',remove_record)
    controls.addStretch()
    refresh=QPushButton('重新读取');refresh.clicked.connect(load);controls.addWidget(refresh)
    close=QPushButton('关闭');close.clicked.connect(dialog.close);controls.addWidget(close)
    table.itemSelectionChanged.connect(update_selection);update_selection()
    dialog.show();load();return dialog


def show_duplicates(window):
    dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.setWindowTitle('重复候选与多版本');dialog.resize(750,480)
    layout=QVBoxLayout(dialog);status=QLabel('正在检查编号和已有完整指纹…');status.setWordWrap(True);layout.addWidget(status);items=QListWidget();layout.addWidget(items)
    closed=[False];dialog.finished.connect(lambda _:closed.__setitem__(0,True));groups=[]
    def ready(result):
        if closed[0]:return
        groups[:]=result;items.clear();items.addItems([group['label'] for group in groups]);status.setText(f'找到 {len(groups)} 组候选。同编号可能是分段或不同版本，文件不会自动删除。')
    def compare():
        index=items.currentRow()
        if 0<=index<len(groups):show_versions(window,groups[index]['work_ids'])
    button=QPushButton('对比选中组');button.clicked.connect(compare);layout.addWidget(button);items.itemDoubleClicked.connect(lambda _:compare())
    dialog.show();window.run_job('检查重复候选',lambda lib,p:duplicate_candidates(lib),ready);return dialog
