"""In-process file pickers; native shell extensions stall on unavailable drives."""
from PySide6.QtWidgets import QFileDialog

OPTIONS = QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.DontResolveSymlinks


def existing_directory(parent, caption, directory=''):
    return QFileDialog.getExistingDirectory(parent, caption, directory,
                                            QFileDialog.Option.ShowDirsOnly | OPTIONS)


def open_file_name(parent, caption, directory='', file_filter=''):
    path, _ = QFileDialog.getOpenFileName(parent, caption, directory, file_filter, options=OPTIONS)
    return path


def save_file_name(parent, caption, directory='', file_filter=''):
    path, _ = QFileDialog.getSaveFileName(parent, caption, directory, file_filter, options=OPTIONS)
    return path
