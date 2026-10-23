"""Request a normal Windows shutdown; never force applications to close."""
import os
from pathlib import Path
import subprocess
import sys


def shutdown_supported():
    return sys.platform == 'win32'


def request_shutdown():
    if not shutdown_supported():
        raise ValueError('远程关机仅支持 Windows')
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'shutdown.exe'
    # /t > 0 implicitly forces applications closed on Windows. Delay inside Lumen
    # instead, then use /t 0 without /f so Windows can protect unsaved documents.
    subprocess.run([str(executable), '/s', '/t', '0'], check=True, capture_output=True,
                   timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
