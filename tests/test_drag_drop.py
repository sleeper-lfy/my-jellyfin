from pathlib import Path
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QMessageBox
from lumen.import_ui import ImportDialog
from lumen.ui import MainWindow


def drag_event(paths, cls=QDragEnterEvent):
    mime = QMimeData();mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    event = cls(QPoint(20, 20), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    event._mime_ref = mime
    return event


class FakeBox:
    StandardButton = QMessageBox.StandardButton
    messages = []

    @staticmethod
    def information(*args):
        FakeBox.messages.append(' '.join(str(a) for a in args[1:]))


def test_drag_enter_accepts_urls_without_disk_probe(qapp, tmp_path, monkeypatch):
    window = MainWindow(tmp_path/'drag-ui')
    probed = []
    monkeypatch.setattr(Path, 'is_dir', lambda self: probed.append(str(self)) or False)
    try:
        event = drag_event([str(tmp_path)])
        window.dragEnterEvent(event)
        assert event.isAccepted()
        assert not [p for p in probed if p.startswith(str(tmp_path))]
    finally:
        monkeypatch.undo();window.close()


def test_drop_opens_dialog_and_handles_files_and_errors(qapp, tmp_path, monkeypatch):
    window = MainWindow(tmp_path/'drop-ui')
    shown = []
    real_show = ImportDialog.show
    monkeypatch.setattr(ImportDialog, 'show', lambda self: (shown.append(True), real_show(self))[1])
    messages = []
    monkeypatch.setattr(MainWindow, 'import_hint', lambda self, text: messages.append(text))
    folder = tmp_path/'a folder';folder.mkdir()
    original_is_dir = Path.is_dir
    mode = {'value': 'vanished'}
    def stub_is_dir(self):
        return False if mode['value'] == 'vanished' else original_is_dir(self)
    monkeypatch.setattr(Path, 'is_dir', stub_is_dir)
    try:
        window.dropEvent(drag_event([str(folder)], QDropEvent))
        assert shown == [] and messages and '没有识别到文件夹' in messages[-1]
        mode['value'] = 'normal'
        window.dropEvent(drag_event([str(tmp_path/'file.txt')], QDropEvent))
        assert shown == [] and '没有识别到文件夹' in messages[-1]
        window.dropEvent(drag_event([str(folder)], QDropEvent))
        assert shown == [True]
        dialog = window.import_form
        assert dialog.path.text().endswith('a folder') and dialog.isVisible()
        window.dropEvent(drag_event([str(folder)], QDropEvent))
        assert shown == [True] and window.status.text() == '导入窗口已打开，请在其中确认设置'
        dialog.showMinimized()
        window.import_path(str(folder))
        assert not dialog.isMinimized() and dialog.isVisible()
    finally:
        window.close()
