import argparse
import logging
import os
import sys
from .core import data_directory


def main():
    if '--plugin-worker' in sys.argv:
        from .js_worker import run as worker
        worker()
        return
    parser = argparse.ArgumentParser(description='Lumen · 私人光影库')
    parser.add_argument('--data-dir', help='Override the local data directory')
    parser.add_argument('--serve', action='store_true', help='Run the authenticated LAN server without the desktop UI')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8097)
    parser.add_argument('--verify-mpv', action='store_true', help='Verify the bundled libmpv and shader resources')
    parser.add_argument('--smoke', action='store_true', help='Render all main pages and exit (for CI)')
    args = parser.parse_args()
    if args.data_dir:
        os.environ['LUMEN_DATA_DIR'] = args.data_dir
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    from .diagnostics import configure_logging
    configure_logging(directory)
    if args.verify_mpv:
        import json
        from pathlib import Path
        from PySide6.QtCore import QCoreApplication
        from .mpv_backend import MpvMedia
        app = QCoreApplication(sys.argv[:1])
        media = MpvMedia(headless=True)
        try:
            media.set_enhancement(True)
            shaders = media.engine.glsl_shaders
            if len(shaders) != 1 or not Path(shaders[0]).is_file():
                raise RuntimeError('Bundled shader missing')
            (directory / 'mpv-check.json').write_text(json.dumps({'version': media.engine.mpv_version, 'shader': True}), encoding='utf-8')
        finally:
            media.shutdown()
        return 0
    if args.serve:
        from .server import LanServer
        import signal
        import threading
        from PySide6.QtCore import QLockFile
        service_lock = QLockFile(str(directory / "app.lock"))
        service_lock.setStaleLockTime(0)
        if not service_lock.tryLock(100):
            print("Lumen is already using this data directory.", file=sys.stderr)
            return 1
        service = LanServer(directory,args.host,args.port)
        service.start()
        stop = threading.Event()
        signal.signal(signal.SIGINT,lambda *_:stop.set())
        signal.signal(signal.SIGTERM,lambda *_:stop.set())
        print(f'Lumen LAN listening on port {service.port}; use the access key from desktop Settings.',flush=True)
        try:
            stop.wait()
        finally:
            service.stop()
            service_lock.unlock()
        return 0
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer, QLockFile
    from .ui import MainWindow
    app = QApplication(sys.argv[:1])
    from .diagnostics import UiWatchdog
    watchdog=UiWatchdog(directory,app)
    app.aboutToQuit.connect(watchdog.stop)
    from PySide6.QtGui import QIcon
    from pathlib import Path
    icon_root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
    app.setWindowIcon(QIcon(str(icon_root/'assets'/'lumen.ico')))
    app.setApplicationName('Lumen')
    app.setOrganizationName('Lumen')
    lock = QLockFile(str(directory / 'app.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, 'Lumen 已运行', '同一数据目录只允许一个应用实例，请切换到已打开的窗口。')
        return 1
    window = MainWindow(directory)
    window.show()
    if sys.platform=='win32' and getattr(sys,'frozen',False) and not args.smoke:
        QTimer.singleShot(15000,lambda:window.updater().startup())
    if args.smoke:
        def check():
            for section in ['home','movie','series','vr','other','discover','stats']:
                window.navigate(section)
                for index in range(window.tabs.count()):
                    window.tabs.setCurrentIndex(index)
                    app.processEvents()
            window.navigate('home')
            def capture_and_close():
                if window._browse_job is not None or window._browse_pending is not None:
                    QTimer.singleShot(20,capture_and_close)
                    return
                window.grab().save(str(directory / 'smoke.png'))
                # A rejected close waits for its workers; Qt quits when the
                # final window actually closes rather than destroying threads.
                window.close()
            QTimer.singleShot(0,capture_and_close)
        QTimer.singleShot(100, check)
    result = app.exec()
    lock.unlock()
    return result
