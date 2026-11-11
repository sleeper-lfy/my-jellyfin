"""Exercise the custom hook before PyInstaller's real PySide6 runtime hook."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'scripts/pyinstaller-hooks/rth_lumen_desktop.py'


@pytest.mark.parametrize('arguments,expected', [
    ([], True),
    (['--background'], True),
    (['--data-dir', r'C:\My library', '--background'], True),
    (['--background', r'--data-dir=C:\Library', '--host=127.0.0.1', '--port', '8097'], True),
    (['--data-dir=--desktop-child'], True),  # a value is not a mode flag
    (['--desktop-child'], False),
    (['--foreground'], False),
    (['--smoke'], False),
    (['--verify-mpv'], False),
    (['--serve'], False),
    (['--background-worker', 'watch'], False),
    (['--image-worker', 'input', 'output'], False),
    (['--plugin-worker', 'input', 'output'], False),
    (['--browser-http-worker', 'input', 'output', 'body'], False),
    (['--background', '--foreground'], False),
    (['--background', '--serve'], False),
    (['--data-dir', '--desktop-child'], False),
    (['--data-dir'], False),
    (['--data-dir='], False),
    (['--background=true'], False),
    (['--back'], False),
    (['--unknown-worker'], False),
    (['--help'], False),
    (['--'], False),
])
def test_only_unambiguous_supervisor_arguments_skip_qt(arguments, expected):
    namespace = runpy.run_path(str(HOOK))
    assert namespace['_lumen_supervisor_arguments'](arguments) is expected


@pytest.mark.parametrize('platform,frozen,meipass,arguments,patched', [
    ('win32', True, True, [], True),
    ('win32', True, True, ['--background'], True),
    ('win32', False, True, ['--background'], False),
    ('win32', True, False, ['--background'], False),
    ('linux', True, True, ['--background'], False),
    ('darwin', True, True, [], False),
    ('win32', True, True, ['--desktop-child'], False),
    ('win32', True, True, ['--foreground'], False),
])
def test_patch_requires_frozen_windows_owner_and_preserves_other_bindings(monkeypatch, platform, frozen, meipass, arguments, patched):
    calls = []

    def original(*values):
        calls.append(values)
        return 'original result'

    qt = ModuleType('_pyi_rth_utils.qt')
    qt.create_embedded_qt_conf = original
    helpers = ModuleType('_pyi_rth_utils')
    helpers.qt = qt
    system = SimpleNamespace(platform=platform, frozen=frozen, argv=['Lumen.exe', *arguments])
    if meipass:
        system._MEIPASS = 'bundle'
    # Executing with an isolated sys object avoids changing pytest's platform.
    source = HOOK.read_text(encoding='utf-8')
    import builtins
    real_import = builtins.__import__

    def isolated_import(name, *args, **kwargs):
        if name == 'sys':
            return system
        return real_import(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, '_pyi_rth_utils', helpers)
    namespace = {'__builtins__': {**vars(builtins), '__import__': isolated_import}}
    exec(compile(source, str(HOOK), 'exec'), namespace)
    assert (qt.create_embedded_qt_conf is not original) is patched
    assert qt.create_embedded_qt_conf('PySide6', 'bundle/PySide6') == (None if patched else 'original result')
    assert calls == ([] if patched else [('PySide6', 'bundle/PySide6')])
    assert qt.create_embedded_qt_conf('OtherBinding', 'other') == 'original result'
    assert calls[-1] == ('OtherBinding', 'other')


STANDARD_SEQUENCE = r'''
import json
import os
import runpy
import sys
from pathlib import Path
import PyInstaller

root = Path(sys.argv[1])
arguments = json.loads(sys.argv[2])
include_custom = json.loads(sys.argv[3])
pyinstaller = Path(PyInstaller.__file__).parent
sys.path.insert(0, str(pyinstaller / 'fake-modules'))
from _pyi_rth_utils import qt
original = qt.create_embedded_qt_conf
native_platform = sys.platform
sys.argv = ['Lumen.exe', *arguments]
sys.frozen = True
sys._MEIPASS = str(root / '.local' / 'nonexistent-hook-fixture-bundle')
# Select the Windows owner hook, then execute the real standard hook with the
# native wheel's platform. This loads real QtCore for GUI cases on Linux too;
# no Qt module, helper or standard-hook implementation is stubbed here.
sys.platform = 'win32'
if include_custom:
    runpy.run_path(str(root / 'scripts/pyinstaller-hooks/rth_lumen_desktop.py'))
patched = qt.create_embedded_qt_conf is not original
sys.platform = native_platform
runpy.run_path(str(pyinstaller / 'hooks/rthooks/pyi_rth_pyside6.py'))
print(json.dumps({
    'patched': patched,
    'qt_core_loaded': 'PySide6.QtCore' in sys.modules,
    'qt_modules': sorted(name for name in sys.modules if name.startswith(('PySide6', 'shiboken6'))),
    'bindings': qt._registered_qt_bindings,
    'plugin_path': os.environ.get('QT_PLUGIN_PATH'),
    'qml_path': os.environ.get('QML2_IMPORT_PATH'),
    'native_platform': native_platform,
    'bundle': sys._MEIPASS,
}))
'''


@pytest.mark.parametrize('arguments,include_custom,expect_qt', [
    ([], True, False),
    (['--background', '--data-dir', r'C:\My library'], True, False),
    (['--background'], False, True),  # reproduce the original eager import
    (['--desktop-child'], True, True),
    (['--foreground'], True, True),
    (['--smoke'], True, True),
    (['--verify-mpv'], True, True),
    (['--serve'], True, True),
    (['--background-worker', 'watch'], True, True),
    (['--image-worker'], True, True),
    (['--plugin-worker'], True, True),
    (['--browser-http-worker'], True, True),
])
def test_real_standard_hook_sequence_imports_qt_only_for_gui_or_workers(arguments, include_custom, expect_qt):
    pytest.importorskip('PyInstaller')
    completed = subprocess.run(
        [sys.executable, '-c', STANDARD_SEQUENCE, str(ROOT), json.dumps(arguments), json.dumps(include_custom)],
        check=True, capture_output=True, text=True, timeout=20,
    )
    state = json.loads(completed.stdout)
    assert state['qt_core_loaded'] is expect_qt, state
    assert state['patched'] is (include_custom and not expect_qt), state
    if not expect_qt:
        assert state['qt_modules'] == [], state
    # Standard hook configuration remains active even for the Qt-free owner.
    assert state['bindings'] == 'PySide6'
    qt_root = Path(state['bundle']) / 'PySide6'
    if not state['native_platform'].startswith('win'):
        qt_root /= 'Qt'
    assert state['plugin_path'] == str(qt_root / 'plugins')
    assert state['qml_path'] == str(qt_root / 'qml')


def test_windows_packaging_includes_the_custom_runtime_hook():
    build = (ROOT / 'scripts/build-windows.ps1').read_text(encoding='utf-8')
    assert '--runtime-hook scripts/pyinstaller-hooks/rth_lumen_desktop.py' in build
