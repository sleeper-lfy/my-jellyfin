"""One background batch with explicit source, scope and overwrite controls."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QLabel, QPushButton, QPlainTextEdit
from .plugins import Plugins
from .actor_batch import fetch_actor_portraits


def show_actor_batch(window):
    existing=getattr(window,'actor_batch_dialog',None)
    if existing is not None:
        existing.raise_();existing.activateWindow();return existing
    dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.actor_batch_dialog=dialog
    dialog.destroyed.connect(lambda:setattr(window,'actor_batch_dialog',None))
    dialog.setWindowTitle('批量自动获取演员头像');dialog.resize(560,350)
    layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
    sources=QComboBox();sources.setObjectName('batchActorSources')
    plugins=[p for p in Plugins(window.library).installed() if p['config'].get('enabled') and 'actors' in p['capabilities']]
    if plugins:
        sources.addItem('按优先级依次尝试所有已启用头像来源',[p['id'] for p in plugins])
        for plugin in plugins:sources.addItem(plugin['name'],[plugin['id']])
    scope=QComboBox();scope.setObjectName('batchActorScope')
    scope.addItem('全部作品的演员',None)
    actors=[item for item in window.current_items if item.get('name') and not item.get('kind')]
    visible=list(dict.fromkeys(name for actor in actors for name in [actor['name'],*actor.get('aliases',[])]))
    if visible:scope.addItem(f'当前演员列表（{len(actors)} 位）',visible)
    overwrite=QCheckBox('覆盖已有头像（锁定的演员资料仍保留）');overwrite.setObjectName('batchActorOverwrite')
    form.addRow('头像来源',sources);form.addRow('获取范围',scope);form.addRow(overwrite)
    note=QLabel('默认只补齐缺失头像。姓名或别名唯一匹配时自动保存；同名、多个候选和无头像结果会跳过，之后可手动确认。\n任务在后台执行，可暂停或停止，已完成的头像会保留。')
    note.setWordWrap(True);layout.addWidget(note)
    start=QPushButton('开始批量获取');start.setObjectName('startBatchActorPhotos');start.setEnabled(bool(plugins));layout.addWidget(start)
    if not plugins:
        note.setText('尚无已启用的头像来源。请先在“刮削演员头像”中安装 / 更新来源，或在设置中启用支持 actors 的插件。')
    setup=QPushButton('管理头像来源…');layout.addWidget(setup)
    def manage():
        from .actor_ui import show_actor_scraper
        dialog.close();show_actor_scraper(window)
    setup.clicked.connect(manage)

    def complete(result):
        if window.detail_page is not None:window.reload_details(window.detail_page.work_id)
        summary=(f"头像更新 {result['updated']} 位 · 跳过 {result['skipped']} 位 · "
                 f"需确认 {result['ambiguous']} 位 · 未匹配 {result['unmatched']} 位 · 失败 {result['failed']} 位")
        window.status.setText(summary)
        report=QDialog(window);report.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        report.setWindowTitle('演员头像批量获取结果');report.resize(720,520)
        body=QVBoxLayout(report);label=QLabel(summary);label.setWordWrap(True);body.addWidget(label)
        rows=result['items'][:500]
        text=QPlainTextEdit('\n'.join(row['name']+'：'+row['reason'] for row in rows));text.setReadOnly(True);body.addWidget(text)
        if len(result['items'])>500:body.addWidget(QLabel('这里只显示前 500 位；完整结果保存在任务记录中。'))
        close=QPushButton('关闭');close.clicked.connect(report.close);body.addWidget(close)
        window.actor_batch_result_dialog=report
        report.show()

    def begin():
        selected=sources.currentData();names=scope.currentData();replace=overwrite.isChecked()
        if not selected:return
        window.run_job('批量获取演员头像',lambda library,progress:fetch_actor_portraits(library,selected,
            names=names,replace=replace,progress=progress,cancelled=progress.cancelled),complete)
        dialog.close()
    start.clicked.connect(begin)
    dialog.show();return dialog
