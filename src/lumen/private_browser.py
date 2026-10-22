"""Open website links in a supported browser's private window, without a shell."""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

_FLAGS = {'msedge': '--inprivate', 'chrome': '--incognito', 'brave': '--incognito',
          'firefox': '--private-window', 'opera': '--private'}


def _windows_candidates():
    import winreg
    # Respect the default HTTPS browser when its command supports a private window.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice') as key:
            association = winreg.QueryValueEx(key, 'ProgId')[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, association + r'\shell\open\command') as key:
            command = winreg.QueryValueEx(key, '')[0]
        match = re.match(r'^\s*(?:"([^"]+)"|(.+?\.exe))(?:\s|$)', command, re.I)
        if match:
            yield os.path.expandvars(match.group(1) or match.group(2))
    except OSError:
        pass
    for executable in _FLAGS:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, rf'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}.exe') as key:
                    yield os.path.expandvars(winreg.QueryValueEx(key, '')[0]).strip('"')
            except OSError:
                pass
    for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        folder = os.environ.get(variable)
        if not folder:
            continue
        for relative in (r'Microsoft\Edge\Application\msedge.exe', r'Google\Chrome\Application\chrome.exe',
                         r'BraveSoftware\Brave-Browser\Application\brave.exe', r'Mozilla Firefox\firefox.exe'):
            yield str(Path(folder) / relative)


def private_commands(url: str):
    """Yield executable/argument lists; never use a desktop opener which may ignore privacy."""
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('只能在无痕浏览器中打开 HTTP / HTTPS 网页地址')
    if sys.platform == 'win32':
        for executable in _windows_candidates():
            flag = _FLAGS.get(Path(executable).stem.lower())
            if flag and Path(executable).is_file():
                yield [executable, flag, url]
    elif sys.platform == 'darwin':
        for executable in ('/Applications/Firefox.app/Contents/MacOS/firefox',
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'):
            flag = '--private-window' if 'Firefox' in executable else '--inprivate' if 'Edge' in executable else '--incognito'
            if Path(executable).is_file():
                yield [executable, flag, url]
    else:
        for browser, flag in (('firefox', '--private-window'), ('microsoft-edge', '--inprivate'),
                ('google-chrome', '--incognito'), ('chromium', '--incognito'),
                ('chromium-browser', '--incognito'), ('brave-browser', '--incognito')):
            executable = shutil.which(browser)
            if executable:
                yield [executable, flag, url]


def open_private(url: str) -> None:
    attempted = set()
    for command in private_commands(url):
        if command[0] in attempted:
            continue
        attempted.add(command[0])
        try:
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            return
        except OSError:
            continue
    raise RuntimeError('未找到可启动的无痕浏览器。请安装 Edge、Chrome、Firefox 或 Brave 后重试。')
