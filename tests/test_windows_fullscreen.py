"""Exercise the Win32/COM boundary without requiring Explorer in Linux CI."""
import ctypes
from ctypes import wintypes
from types import SimpleNamespace
import pytest
from lumen import windows_fullscreen as native


class Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


@pytest.mark.parametrize('com_result', [0, 1, -2147417850])  # S_OK, S_FALSE, RPC_E_CHANGED_MODE
def test_shell_fullscreen_marker_and_com_lifetime(monkeypatch, com_result):
    calls = []
    prototype = ctypes.CFUNCTYPE  # WINAPI on Windows; portable callback ABI for this fake COM object.
    callbacks = [prototype(wintypes.ULONG, ctypes.c_void_p)(lambda _: calls.append('release') or 1),
                 prototype(ctypes.c_long, ctypes.c_void_p)(lambda _: 0),
                 prototype(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, wintypes.BOOL)(
                     lambda _, hwnd, enabled: calls.append((hwnd, bool(enabled))) or 0)]
    table = (ctypes.c_void_p * 9)()
    for index, callback in zip((2, 3, 8), callbacks):
        table[index] = ctypes.cast(callback, ctypes.c_void_p)
    interface = ctypes.pointer(ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p)))

    def create(clsid, outer, context, iid, output):
        assert ctypes.string_at(clsid, 16) == bytes.fromhex('44f3fd566dfdd011958a006097c9a090')
        assert ctypes.string_at(iid, 16) == bytes.fromhex('95492d603ab19b42a66e1935e44f4317')
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.cast(interface, ctypes.c_void_p)
        return 0

    api = SimpleNamespace(CoInitializeEx=Function(lambda *_: com_result), CoCreateInstance=Function(create),
                          CoUninitialize=Function(lambda: calls.append('uninitialize')))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda _: api, raising=False)
    monkeypatch.setattr(ctypes, 'WINFUNCTYPE', prototype, raising=False)
    hwnd = 0x123456789  # Detect HWND truncation on a 64-bit process.
    native._mark_fullscreen(wintypes.HWND(hwnd), True)
    native._mark_fullscreen(wintypes.HWND(hwnd), False)
    assert [c for c in calls if isinstance(c, tuple)] == [(hwnd, True), (hwnd, False)]
    assert calls.count('release') == 2
    assert calls.count('uninitialize') == (2 if com_result >= 0 else 0)


def test_fullscreen_covers_physical_secondary_monitor_and_never_hides_global_taskbar(monkeypatch):
    monkeypatch.setattr(native.sys, 'platform', 'win32')
    marks, positions = [], []
    monkeypatch.setattr(native, '_mark_fullscreen', lambda hwnd, enabled: marks.append((hwnd.value, enabled)))
    def monitor_info(_, output):
        # A secondary monitor left of the primary with a taskbar at the bottom.
        info = output._obj
        info.monitor = wintypes.RECT(-3440, -200, 0, 1240)
        info.work = wintypes.RECT(-3440, -200, 0, 1176)
        return True
    api = SimpleNamespace(MonitorFromWindow=Function(lambda *_: 10), GetMonitorInfoW=Function(monitor_info),
                          GetWindowRect=Function(lambda *_: False),
                          SetWindowPos=Function(lambda *args: positions.append(args) or True))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *_, **__: api, raising=False)
    native.set_fullscreen_window(0x123456789, True)
    native.set_fullscreen_window(0x123456789, False)
    assert marks == [(0x123456789, True), (0x123456789, False)]
    assert len(positions) == 1  # Exiting leaves geometry restoration to Qt.
    hwnd, z_order, x, y, width, height, flags = positions[0]
    assert hwnd.value == 0x123456789 and z_order is None  # HWND_TOP, never HWND_TOPMOST.
    assert (x, y, width, height) == (-3440, -200, 3440, 1440)
    assert flags == 0x210
    def already_full(_,output):
        output._obj.left=-3440;output._obj.top=-200;output._obj.right=0;output._obj.bottom=1240;return True
    api.GetWindowRect=Function(already_full)
    native.set_fullscreen_window(0x123456789,True)
    assert len(positions)==1  # Repeated Qt state events must not invalidate the native surface.
