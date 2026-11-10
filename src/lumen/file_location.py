"""Open an existing video's location with argument-safe native platform APIs."""
from pathlib import Path
import sys
from PySide6.QtCore import QProcess, QUrl
from PySide6.QtGui import QDesktopServices


def reveal_video(path):
    target=Path(path).expanduser()
    if not target.is_file():
        raise FileNotFoundError('视频文件不存在或已离线：'+str(target))
    target=target.resolve()
    if sys.platform=='win32':
        ok,_=QProcess.startDetached('explorer.exe',['/select,',str(target)])
    elif sys.platform=='darwin':
        ok,_=QProcess.startDetached('open',['-R',str(target)])
    else:
        ok=QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))
    if not ok:
        raise OSError('无法打开系统文件管理器')
    return target
