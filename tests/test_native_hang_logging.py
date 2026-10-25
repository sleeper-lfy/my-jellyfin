"""A native call holding Python's GIL must still leave usable stall evidence."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_native_stall_is_logged_even_when_python_monitor_cannot_acquire_gil(tmp_path):
    script=textwrap.dedent('''
        import ctypes,os,sys
        from pathlib import Path
        from PySide6.QtCore import QCoreApplication,QTimer
        from lumen.diagnostics import UiWatchdog
        app=QCoreApplication([])
        watchdog=UiWatchdog(Path(sys.argv[1]),app)
        def native_stall():
            # PyDLL intentionally retains the GIL, like the captured Qt wait.
            if os.name=='nt':ctypes.PyDLL('kernel32').Sleep(7000)
            else:ctypes.PyDLL(None).sleep(7)
        QTimer.singleShot(1500,native_stall)
        QTimer.singleShot(9500,app.quit)
        app.exec();watchdog.stop();watchdog.thread.join(2)
    ''')
    environment={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True,text=True,env=environment,timeout=18)
    assert result.returncode==0,result.stderr
    recorded=(tmp_path/'ui-native-hangs.log').read_text()
    assert 'Timeout' in recorded and 'native_stall' in recorded
