"""Explicitly merge logical Fans author groups without moving media."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QDialogButtonBox,QMessageBox
from .background import run_background
from .core import Library


def merge_author_folders(detail):
    window=detail.window;target_id=detail.work_id
    def read(job):
        library=Library(window.library.directory,initialize=False)
        try:return [work for work in library.query({'kinds':['fans']}) if work['id']!=target_id]
        finally:library.close()
    def ready(records):
        if window.detail_page is not detail or window._closing:return
        if not records:
            QMessageBox.information(window,'合并同作者文件夹','还没有其他 Fans 作者条目。导入其他目录后，可在这里合并同一作者。');return
        dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.setWindowTitle('合并同作者文件夹');dialog.resize(650,480)
        layout=QVBoxLayout(dialog);note=QLabel('选择属于同一作者的条目，合并到当前作者。只合并媒体库记录，原始目录和视频保留，观看记录及书签一并保留。');note.setWordWrap(True);layout.addWidget(note)
        layout.addWidget(QLabel('合并后的作者名称'))
        name=QLineEdit(detail.work['metadata'].get('creator') or detail.work['title']);name.setObjectName('fansMergeCreator');layout.addWidget(name)
        choices=QListWidget();choices.setObjectName('fansMergeChoices');layout.addWidget(choices)
        for work in records:
            item=QListWidgetItem(f"{work['title']} · {len(work['files'])} 个视频");item.setData(Qt.ItemDataRole.UserRole,work['id']);item.setCheckState(Qt.CheckState.Unchecked)
            item.setToolTip('\n'.join(work['metadata'].get('fans_roots',[])));choices.addItem(item)
        message=QLabel('勾选要并入当前作者的条目。');message.setWordWrap(True);layout.addWidget(message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('合并到当前作者');layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
        def merge():
            ids=[choices.item(i).data(Qt.ItemDataRole.UserRole) for i in range(choices.count()) if choices.item(i).checkState()==Qt.CheckState.Checked]
            creator=name.text().strip()
            if not ids or not creator:message.setText('请勾选至少一个条目并填写作者名称。');return
            dialog.accept()
            def complete(result):
                window.status.setText(f"Fans 作者已合并：{result['creator']} · {result['files']} 个视频")
                if window.detail_page is not None and window.detail_page.work_id==target_id:window.reload_details(target_id)
            window.run_job('合并 Fans 作者文件夹',lambda library,progress:library.merge_fans_folders(ids,target_id,creator=creator),complete)
        buttons.accepted.connect(merge);dialog.open()
    window.status.setText('正在后台读取 Fans 作者条目…')
    return run_background(window,read,ready,lambda error:window.status.setText('读取 Fans 作者失败：'+error))
