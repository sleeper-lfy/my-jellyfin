import subprocess
from pathlib import PureWindowsPath
from types import SimpleNamespace

import pytest

from lumen import startup


class Registry:
    HKEY_CURRENT_USER = object()
    KEY_QUERY_VALUE = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.operations = []
        self.fail_write = False
        self.fail_read = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def OpenKey(self, root, key, reserved, access):
        assert root is self.HKEY_CURRENT_USER and key == startup.RUN_KEY and reserved == 0
        self.operations.append(('open', access))
        if self.fail_read and access == self.KEY_QUERY_VALUE:
            raise PermissionError('denied')
        return self

    def CreateKeyEx(self, root, key, reserved, access):
        assert root is self.HKEY_CURRENT_USER and key == startup.RUN_KEY and reserved == 0
        assert access == self.KEY_SET_VALUE
        self.operations.append(('create', access))
        return self

    def QueryValueEx(self, key, name):
        assert key is self and name == startup.RUN_VALUE
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, command):
        assert key is self and reserved == 0 and kind == self.REG_SZ
        if self.fail_write:
            raise PermissionError('denied')
        self.operations.append(('set', name, command))
        self.values[name] = command, kind

    def DeleteValue(self, key, name):
        assert key is self
        if self.fail_write:
            raise PermissionError('denied')
        self.operations.append(('delete', name))
        del self.values[name]


@pytest.fixture
def installation(tmp_path_factory, monkeypatch):
    # The ordinary registration tests must fit Windows Run's command limit;
    # function-named tmp_path directories otherwise consume the budget twice.
    root = tmp_path_factory.mktemp('su')
    executable = root / '安装 & app' / 'Lumen.exe'
    executable.parent.mkdir()
    executable.write_bytes(b'MZ')
    directory = root / '资料 & db'
    directory.mkdir()
    command = subprocess.list2cmdline([str(executable), '--background', '--data-dir', str(directory)])
    assert len(command.encode('utf-16-le')) // 2 <= startup.MAX_COMMAND_LENGTH
    # Also guard the fixture names against a longer Windows CI temp root,
    # even when this suite is running under a shorter POSIX temp directory.
    windows_root = PureWindowsPath(
        r'C:\Users\runneradmin\AppData\Local\Temp\pytest-of-runneradmin\pytest-999999\su999999')
    windows_command = subprocess.list2cmdline([
        str(windows_root / executable.parent.name / executable.name),
        '--background', '--data-dir', str(windows_root / directory.name)])
    assert len(windows_command.encode('utf-16-le')) // 2 <= startup.MAX_COMMAND_LENGTH
    registry = Registry()
    monkeypatch.setattr(startup, 'sys', SimpleNamespace(platform='win32', frozen=True, executable=str(executable)))
    monkeypatch.setattr(startup, '_registry', lambda: registry)
    return executable, directory, registry


def test_status_is_read_only_and_startup_is_opt_in(installation):
    _, directory, registry = installation
    registry.values['Other application'] = ('unchanged', registry.REG_SZ)
    initial = dict(registry.values)
    assert startup.status(directory) == startup.StartupStatus(
        True, False, '默认关闭；开启后登录 Windows 自动后台待机，关闭窗口进入托盘。')
    assert registry.values == initial
    assert all(operation[0] == 'open' for operation in registry.operations)


def test_registration_quotes_fixed_arguments_and_only_uses_hkcu(installation):
    executable, directory, registry = installation
    registry.values['Other application'] = ('do not remove', registry.REG_SZ)
    startup.set_enabled(directory, True)
    expected = subprocess.list2cmdline([str(executable), '--background', '--data-dir', str(directory)])
    assert registry.values == {
        'Other application': ('do not remove', registry.REG_SZ),
        startup.RUN_VALUE: (expected, registry.REG_SZ),
    }
    assert '--background --data-dir' in expected
    assert startup.status(directory).enabled
    writes = list(registry.operations)
    startup.set_enabled(directory, True)
    assert [value for value in registry.operations[len(writes):] if value[0] in ('create', 'set', 'delete')] == []
    startup.set_enabled(directory, False)
    assert registry.values == {'Other application': ('do not remove', registry.REG_SZ)}
    assert not startup.status(directory).enabled


def test_switching_data_directory_is_explicit_and_does_not_delete_other_scope(installation):
    executable, directory, registry = installation
    other = directory.parent / 'Other library'
    other.mkdir()
    startup.set_enabled(other, True)
    before = dict(registry.values)
    state = startup.status(directory)
    assert state.supported and not state.enabled and '其他数据目录' in state.description
    with pytest.raises(startup.StartupError, match='其他数据目录'):
        startup.set_enabled(directory, False)
    assert registry.values == before
    startup.set_enabled(directory, True)
    assert registry.values[startup.RUN_VALUE][0] == subprocess.list2cmdline(
        [str(executable), '--background', '--data-dir', str(directory)])


@pytest.mark.parametrize('command', [
    '"C:\\Other Install\\Lumen.exe" --background --data-dir "C:\\Other data"',
    '"C:\\Other\\Unrelated.exe" --background --data-dir C:\\data',
    'cmd /c echo Lumen',
])
def test_foreign_install_or_unrecognized_run_entry_is_never_overwritten(installation, command):
    _, directory, registry = installation
    registry.values[startup.RUN_VALUE] = command, registry.REG_SZ
    before = dict(registry.values)
    assert not startup.status(directory).supported
    for enabled in (True, False):
        with pytest.raises(startup.StartupError, match='其他安装或命令'):
            startup.set_enabled(directory, enabled)
        assert registry.values == before


def test_registry_errors_surface_without_claiming_a_changed_setting(installation):
    _, directory, registry = installation
    registry.fail_write = True
    with pytest.raises(startup.StartupError, match='注册表权限'):
        startup.set_enabled(directory, True)
    assert not registry.values and not startup.status(directory).enabled
    registry.fail_write = False
    startup.set_enabled(directory, True)
    registry.fail_write = True
    with pytest.raises(startup.StartupError, match='注册表权限'):
        startup.set_enabled(directory, False)
    assert startup.status(directory).enabled
    registry.fail_read = True
    state = startup.status(directory)
    assert not state.supported and not state.enabled and '无法读取' in state.description


def test_non_string_registry_value_is_preserved(installation):
    _, directory, registry = installation
    registry.values[startup.RUN_VALUE] = ('%SOME_VAR%\\Lumen.exe', 2)
    before = dict(registry.values)
    assert not startup.status(directory).supported
    with pytest.raises(startup.StartupError, match='格式不同'):
        startup.set_enabled(directory, True)
    assert registry.values == before


@pytest.mark.parametrize('platform,frozen', [('linux', True), ('win32', False)])
def test_source_or_non_windows_is_disabled_without_registry_access(installation, monkeypatch, platform, frozen):
    _, directory, registry = installation
    startup.sys.platform = platform
    startup.sys.frozen = frozen
    monkeypatch.setattr(startup, '_registry', lambda: pytest.fail('unsupported platform touched registry'))
    state = startup.status(directory)
    assert not state.supported and not state.enabled and '安装版' in state.description
    with pytest.raises(startup.StartupError, match='安装版'):
        startup.set_enabled(directory, True)
    assert not registry.operations


@pytest.mark.parametrize('invalid', ['relative/data', '', 'C:relative', 'bad\x00path', 'bad"path', '/bad:stream', '/CON'])
def test_invalid_paths_are_rejected_before_registry_writes(installation, invalid):
    _, _, registry = installation
    with pytest.raises(startup.StartupError):
        startup.set_enabled(invalid, True)
    assert not registry.operations


def test_missing_wrong_executable_and_overlong_commands_are_rejected(installation):
    executable, directory, registry = installation
    with pytest.raises(startup.StartupError):
        startup.command_line(directory / 'missing', executable)
    wrong = executable.with_name('pythonw.exe')
    wrong.write_bytes(b'python')
    with pytest.raises(startup.StartupError, match='Lumen.exe'):
        startup.command_line(directory, wrong)
    deep = directory / ('a' * 70) / ('b' * 70)
    deep.mkdir(parents=True)
    with pytest.raises(startup.StartupError, match='260'):
        startup.set_enabled(deep, True)
    assert not registry.operations


def test_settings_checkbox_restores_actual_registry_state_after_write_failure(installation, monkeypatch):
    from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel
    from lumen.startup_ui import StartupSettings

    application = QApplication.instance() or QApplication([])
    _, directory, registry = installation
    dialog = QDialog()
    dialog.library = SimpleNamespace(directory=directory)
    dialog.startup = QCheckBox(dialog)
    dialog.startup_status = QLabel(dialog)
    dialog.refresh_startup = lambda: StartupSettings.refresh_startup(dialog)
    warnings = []
    monkeypatch.setattr('lumen.startup_ui.QMessageBox.warning', lambda *args: warnings.append(args[1:]))
    dialog.refresh_startup()
    dialog.startup.toggled.connect(lambda enabled: StartupSettings.change_startup(dialog, enabled))
    registry.fail_write = True
    dialog.startup.setChecked(True)
    assert not dialog.startup.isChecked() and dialog.startup.isEnabled()
    assert len(warnings) == 1 and '注册表权限' in warnings[0][1]
    registry.fail_write = False
    dialog.startup.setChecked(True)
    assert dialog.startup.isChecked() and startup.status(directory).enabled
    registry.fail_write = True
    dialog.startup.setChecked(False)
    assert dialog.startup.isChecked() and startup.status(directory).enabled
    assert len(warnings) == 2  # rollback does not recursively retry the write
    registry.fail_read = True
    dialog.startup.setChecked(False)
    assert dialog.startup.isChecked() and not dialog.startup.isEnabled()
    assert '无法读取' in dialog.startup_status.text() and len(warnings) == 3
    dialog.close()
    application.processEvents()


@pytest.mark.parametrize('value,expected',[(True,True),(False,False),('false',False),('true',False),(1,False),(None,False)])
def test_silent_preference_is_persistent_and_only_boolean_true_hides_window(library,value,expected):
    library.set_setting(startup.SILENT_START_SETTING,value)
    assert startup.silent_start_enabled(library.directory) is expected


def test_silent_start_read_does_not_load_qt_or_image_toolkits(library):
    import os,sys
    from pathlib import Path
    library.set_setting(startup.SILENT_START_SETTING,True)
    code='import sys; from lumen.startup import silent_start_enabled; assert silent_start_enabled(sys.argv[1]); assert not any(name.startswith(("PySide6","PIL")) for name in sys.modules)'
    result=subprocess.run([sys.executable,'-c',code,str(library.directory)],env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'src')},capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_startup_page_is_visible_and_silent_mode_is_independent_of_login_registration(installation,qapp,monkeypatch):
    import sqlite3
    from PySide6.QtWidgets import QTabWidget,QWidget
    from lumen.core import Library
    from lumen.settings import Settings
    _,directory,registry=installation
    # Settings needs a host and database; this flow does not need a video/audio
    # backend. Other UI regressions still exercise the actual MainWindow.
    window=QWidget();window.library=Library(directory);window.lan_server=None
    window.updater=lambda:SimpleNamespace(panel=lambda parent:QWidget(parent))
    dialog=Settings(window)
    try:
        tabs=dialog.findChild(QTabWidget);assert tabs.tabText(0)=='启动与后台'
        panel=dialog.startup_page
        assert panel.silent_startup.isEnabled() and not panel.silent_startup.isChecked()
        panel.silent_startup.setChecked(True)
        assert startup.silent_start_enabled(directory) and not registry.values
        panel.startup.setChecked(True)
        assert startup.status(directory).enabled and startup.silent_start_enabled(directory)
        reloaded=Settings(window)
        try:assert reloaded.startup_page.silent_startup.isChecked() and reloaded.startup_page.startup.isChecked()
        finally:reloaded.close()
        original=window.library.set_setting;errors=[]
        def save(key,value):
            if key==startup.SILENT_START_SETTING:raise sqlite3.OperationalError('database is locked')
            return original(key,value)
        monkeypatch.setattr(window.library,'set_setting',save)
        monkeypatch.setattr('lumen.startup_ui.QMessageBox.warning',lambda *args:errors.append(args[-1]))
        panel.silent_startup.setChecked(False)
        assert panel.silent_startup.isChecked() and startup.silent_start_enabled(directory)
        assert errors==['database is locked'] and startup.status(directory).enabled
    finally:dialog.close();window.close();window.library.close();qapp.processEvents()
