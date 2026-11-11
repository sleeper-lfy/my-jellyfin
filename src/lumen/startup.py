"""Opt-in, per-user Windows startup registration (no GUI or shell dependency)."""

from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath
import ntpath
import subprocess
import sys


RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_VALUE = 'Lumen'
MAX_COMMAND_LENGTH = 260


class StartupError(ValueError):
    pass


@dataclass(frozen=True)
class StartupStatus:
    supported: bool
    enabled: bool
    description: str


def unavailable_reason():
    if sys.platform != 'win32':
        return '仅 Windows 安装版支持开机自启动。'
    if not getattr(sys, 'frozen', False):
        return '源码运行不支持开机自启动，请使用 Windows 安装版。'
    return ''


def _path(value, *, executable=False):
    try:
        raw = os.fspath(value)
        if not isinstance(raw, str) or not raw or any(ord(char) < 32 or char in '"<>|?*' for char in raw):
            raise StartupError('自启动路径包含无效字符。')
        path = Path(raw)
        if not path.is_absolute():
            raise StartupError('自启动程序和数据目录必须使用绝对路径。')
        windows = PureWindowsPath(raw)
        if ':' in ntpath.splitdrive(raw)[1] or any(
                part.endswith((' ', '.')) or PureWindowsPath(part).is_reserved()
                for part in windows.parts if part != windows.anchor):
            raise StartupError('自启动路径不是有效的 Windows 文件路径。')
        # Resolve links before storing an OS-global setting, never depend on CWD.
        path = path.resolve(strict=True)
        if executable:
            if path.name.casefold() != 'lumen.exe' or not path.is_file():
                raise StartupError('自启动仅支持已安装的 Lumen.exe。')
        elif not path.is_dir():
            raise StartupError('自启动数据目录不存在。')
        return path
    except (OSError, RuntimeError, TypeError) as error:
        raise StartupError('自启动路径不可用，请检查程序和数据目录。') from error


def command_line(data_dir, executable=None):
    application = _path(executable or sys.executable, executable=True)
    directory = _path(data_dir)
    command = subprocess.list2cmdline([str(application), '--background', '--data-dir', str(directory)])
    # Windows documents a 260-character limit for Run/RunOnce command lines.
    if len(command.encode('utf-16-le')) // 2 > MAX_COMMAND_LENGTH:
        raise StartupError('自启动命令超过 Windows 的 260 字符限制，请使用较短的安装或数据目录。')
    return command


def _registry():
    import winreg
    return winreg


def _read(registry):
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_QUERY_VALUE) as key:
            value, kind = registry.QueryValueEx(key, RUN_VALUE)
        if kind != registry.REG_SZ or not isinstance(value, str):
            raise StartupError('现有 Lumen 自启动项格式不同，未对其进行修改。')
        return value
    except FileNotFoundError:
        return None


def _same_application(command, executable):
    # Recognize only the fixed arguments we write; never execute/expand values.
    prefix = subprocess.list2cmdline([str(executable)]) + ' --background --data-dir '
    return command.casefold().startswith(prefix.casefold()) and bool(command[len(prefix):])


def status(data_dir):
    reason = unavailable_reason()
    if reason:
        return StartupStatus(False, False, reason)
    try:
        expected = command_line(data_dir)
        current = _read(_registry())
        if current == expected:
            return StartupStatus(True, True, '已启用：登录 Windows 后使用当前数据目录在后台待机。')
        if current is not None:
            if not _same_application(current, _path(sys.executable, executable=True)):
                return StartupStatus(False, False, '同名自启动项属于其他安装或命令，已保留；请在对应安装中管理。')
            return StartupStatus(True, False, '此安装已为其他数据目录启用自启动；勾选后将切换到当前数据目录。')
        return StartupStatus(True, False, '默认关闭；开启后登录 Windows 自动后台待机，关闭窗口进入托盘。')
    except (StartupError, OSError) as error:
        return StartupStatus(False, False, '无法读取自启动设置：' + str(error))


def set_enabled(data_dir, enabled):
    reason = unavailable_reason()
    if reason:
        raise StartupError(reason)
    try:
        expected = command_line(data_dir)
        registry = _registry()
        current = _read(registry)
        application = _path(sys.executable, executable=True)
        if current is not None and not _same_application(current, application):
            raise StartupError('同名自启动项属于其他安装或命令，已保留，无法覆盖。')
        if enabled:
            if current != expected:
                with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                    registry.SetValueEx(key, RUN_VALUE, 0, registry.REG_SZ, expected)
        elif current == expected:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                registry.DeleteValue(key, RUN_VALUE)
        elif current is not None:
            raise StartupError('自启动项已切换到其他数据目录，未删除该设置。')
    except OSError as error:
        raise StartupError('无法保存 Windows 自启动设置，请检查当前用户的注册表权限。') from error
