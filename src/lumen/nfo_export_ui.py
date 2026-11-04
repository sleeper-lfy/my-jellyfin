"""Explicit preview and background export of current library metadata."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QPlainTextEdit,QPushButton
from .nfo_export import preview_export, export_works


def export_dialog(window, work_ids):
    identifiers = list(dict.fromkeys(work_ids))
    dialog = QDialog(window)
    dialog.setWindowTitle('导出 NFO 与本地图片'); dialog.resize(740, 540)
    layout = QVBoxLayout(dialog)
    note = QLabel(f'本次导出范围：{len(identifiers)} 部作品。资料写入各自视频所在目录，供 Jellyfin / Kodi 或重新建库使用。不会移动视频，也不会修改媒体库资料。')
    note.setWordWrap(True); layout.addWidget(note)
    images = QCheckBox('包含已缓存的图片'); images.setChecked(True);images.setToolTip('导出已缓存的海报、演员头像与剧照，不联网下载。');layout.addWidget(images)
    overwrite = QCheckBox('更新已有文件（先备份）');overwrite.setToolTip('更新已有 NFO / 同名图片，保留 NFO 的未知字段。');layout.addWidget(overwrite)
    help_text=QLabel('默认跳过已有文件。图片包含缓存的海报、演员头像与剧照。更新时先在原目录备份，保留 NFO 的未知字段；冲突或文件变化时停止该项并报告。')
    help_text.setWordWrap(True);layout.addWidget(help_text)
    report = QPlainTextEdit(); report.setReadOnly(True); layout.addWidget(report)
    status = QLabel('先检查导出路径，或直接导出。'); status.setWordWrap(True); layout.addWidget(status)
    row = QHBoxLayout(); layout.addLayout(row)
    preview = QPushButton('检查导出路径'); save = QPushButton(f'导出 {len(identifiers)} 部');save.setObjectName('primary'); close = QPushButton('关闭')
    for button in (preview, save, close): row.addWidget(button)
    close.clicked.connect(dialog.reject)
    if not identifiers:preview.setEnabled(False);save.setEnabled(False);status.setText('没有选中的影片。')

    def run(preview_only):
        replace, pictures = overwrite.isChecked(), images.isChecked()
        preview.setEnabled(False); save.setEnabled(False); overwrite.setEnabled(False); images.setEnabled(False)
        status.setText('任务已加入后台队列…')
        def complete(result):
            if not dialog.isVisible(): return
            preview.setEnabled(True); save.setEnabled(True); overwrite.setEnabled(True); images.setEnabled(True)
            if preview_only:
                status.setText(f"将写入 {len(result['paths'])} 个文件 · 跳过 {len(result['skipped'])} 个 · 错误 {len(result['errors'])} 项")
                lines=['写入：'+path for path in result['paths']]+['跳过：'+path for path in result['skipped']]
            else:
                status.setText(f"已写入 {result['written']} 个文件 · 跳过 {result['skipped']} 个 · 备份 {len(result['backups'])} 个 · 错误 {len(result['errors'])} 项")
                lines=['备份：'+path for path in result['backups']]
            lines += ['错误：'+str(item) for item in result['errors']]
            lines += ['提示：'+str(item) for item in result['warnings']]
            report.setPlainText('\n'.join(lines[:1000]) + ('\n仅显示前 1000 项；完整结果见任务记录。' if len(lines)>1000 else ''))
        def action(library, progress):
            if preview_only:
                return preview_export(library, identifiers, overwrite=replace, images=pictures, cancelled=progress.cancelled)
            return export_works(library, identifiers, overwrite=replace, images=pictures, progress=progress, cancelled=progress.cancelled)
        window.run_job('检查 NFO 导出路径' if preview_only else '导出 NFO 与本地图片', action, complete)
    preview.clicked.connect(lambda:run(True)); save.clicked.connect(lambda:run(False))
    dialog.exec(); dialog.deleteLater()
