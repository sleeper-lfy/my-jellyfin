"""In-process file pickers; native shell extensions stall on unavailable drives."""
from PySide6.QtWidgets import QFileDialog

OPTIONS = QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.DontResolveSymlinks
# The app stylesheet recolors text globally but the dialog's item views keep the light
# system base; give the picker its own dark surfaces or it renders white-on-white.
DARK = ('QFileDialog { background: #181818; color: #eeeeee; } '
        'QListView, QTreeView, QTableView { background: #202020; color: #eeeeee; '
        'alternate-background-color: #242424; selection-background-color: #00a4dc; selection-color: #ffffff; '
        'border: 1px solid #303030; } '
        'QLineEdit, QComboBox { background: #252525; color: #ffffff; border: 1px solid #404040; padding: 6px; } '
        'QComboBox QAbstractItemView { background: #222222; selection-background-color: #333333; } '
        'QLabel { color: #cccccc; } QHeaderView::section { background: #282828; color: #cccccc; } '
        'QPushButton { background: #292929; color: #eeeeee; border: 1px solid #404040; border-radius: 3px; padding: 6px 14px; } '
        'QPushButton:hover { border-color: #00a4dc; }')


def _picker(parent, caption, directory=''):
    dialog = QFileDialog(parent, caption, directory)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setOption(QFileDialog.Option.DontResolveSymlinks, True)
    dialog.setStyleSheet(DARK)
    return dialog


def existing_directory(parent, caption, directory=''):
    dialog = _picker(parent, caption, directory)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    if dialog.exec():
        return dialog.selectedFiles()[0]
    return ''


def open_file_name(parent, caption, directory='', file_filter=''):
    dialog = _picker(parent, caption, directory)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    if file_filter:
        dialog.setNameFilter(file_filter)
    if dialog.exec():
        return dialog.selectedFiles()[0]
    return ''


def save_file_name(parent, caption, directory='', file_filter=''):
    dialog = _picker(parent, caption, directory)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    if file_filter:
        dialog.setNameFilter(file_filter)
    if directory:
        dialog.selectFile(directory)
    if dialog.exec():
        return dialog.selectedFiles()[0]
    return ''
