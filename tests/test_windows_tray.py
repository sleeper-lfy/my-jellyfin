import ctypes
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest

from lumen import windows_tray as tray


class FakeWin32:
    def __init__(self, events=(), choices=()):
        self.events = queue.Queue()
        for message, wparam, lparam in events:
            self.events.put((message, wparam, lparam))
        self.choices = iter(choices)
        self.calls = []
        self.hwnd = 0x123456789 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x12345
        self.instance = self.hwnd + 3
        self.icon = self.hwnd + 4
        self.menu = self.hwnd + 5
        self.proc = None
        self.quitting = False
        self.dispatching = False
        self.created = threading.Event()
        self.waiting = threading.Event()
        self.fail_add_at = None
        self.add_count = 0
        self.fail_get_message = False

    def GetModuleHandleW(self, _):
        return self.instance

    def RegisterWindowMessageW(self, name):
        assert name == "TaskbarCreated"
        return 0xC123

    def LoadIconW(self, instance, resource):
        return self.icon

    def LoadImageW(self, *args):
        self.calls.append(("load_image", args))
        return self.icon

    def RegisterClassW(self, pointer):
        value = ctypes.cast(pointer, ctypes.POINTER(tray.WNDCLASSW)).contents
        self.proc = value.lpfnWndProc
        assert value.hInstance == self.instance
        self.calls.append(("register",))
        return 1

    def CreateWindowExW(self, *args):
        assert args[8] is None, "TaskbarCreated requires a hidden top-level window"
        assert args[10] == self.instance
        self.created.set()
        return self.hwnd

    def Shell_NotifyIconW(self, operation, pointer):
        data = ctypes.cast(pointer, ctypes.POINTER(tray.NOTIFYICONDATAW)).contents
        assert data.hWnd == self.hwnd
        assert data.hIcon == self.icon
        assert data.cbSize == ctypes.sizeof(tray.NOTIFYICONDATAW)
        self.calls.append(("notify", operation))
        if operation == tray.NIM_ADD:
            self.add_count += 1
            if self.fail_add_at == self.add_count:
                return 0
        return 1

    def GetMessageW(self, pointer, *args):
        if self.fail_get_message:
            return -1
        if self.quitting:
            return 0
        self.waiting.set()
        message, wparam, lparam = self.events.get(timeout=3)
        value = ctypes.cast(pointer, ctypes.POINTER(tray.MSG)).contents
        value.hwnd, value.message = self.hwnd, message
        value.wParam, value.lParam = wparam, lparam
        return 1

    def TranslateMessage(self, pointer):
        return 1

    def DispatchMessageW(self, pointer):
        value = ctypes.cast(pointer, ctypes.POINTER(tray.MSG)).contents
        self.dispatching = True
        try:
            return self.proc(value.hwnd, value.message, value.wParam, value.lParam)
        finally:
            self.dispatching = False

    def DefWindowProcW(self, *args):
        return 0

    def PostMessageW(self, hwnd, message, wparam, lparam):
        assert hwnd == self.hwnd
        self.calls.append(("post", message))
        self.events.put((message, wparam, lparam))
        return 1

    def PostQuitMessage(self, code):
        self.quitting = True

    def DestroyWindow(self, hwnd):
        self.calls.append(("destroy_window",))
        self.proc(hwnd, tray.WM_DESTROY, 0, 0)
        return 1

    def DestroyIcon(self, icon):
        self.calls.append(("destroy_icon",))
        return 1

    def UnregisterClassW(self, name, instance):
        self.calls.append(("unregister",))
        return 1

    def CreatePopupMenu(self):
        return self.menu

    def AppendMenuW(self, menu, flags, command, text):
        assert menu == self.menu
        self.calls.append(("menu_item", command, text))
        return 1

    def GetCursorPos(self, pointer):
        point = ctypes.cast(pointer, ctypes.POINTER(tray.POINT)).contents
        point.x, point.y = 100, 200
        return 1

    def SetForegroundWindow(self, hwnd):
        return 1

    def TrackPopupMenu(self, menu, *args):
        self.calls.append(("popup",))
        return next(self.choices, 0)

    def DestroyMenu(self, menu):
        self.calls.append(("destroy_menu",))
        return 1


def native(monkeypatch, fake):
    monkeypatch.setattr(tray.sys, "platform", "win32")
    monkeypatch.setattr(tray, "_Win32", lambda: fake)


def test_menu_and_double_click_dispatch_outside_the_native_callback_and_cleanup(monkeypatch):
    fake = FakeWin32([
        (tray.WM_TRAYICON, 0, tray.WM_RBUTTONUP | (1 << 16)),
        (tray.WM_TRAYICON, 0, tray.WM_LBUTTONDBLCLK | (1 << 16)),
        (tray.WM_TRAYICON, 0, tray.WM_CONTEXTMENU | (1 << 16)),
    ], [tray.MENU_OPEN, tray.MENU_EXIT])
    native(monkeypatch, fake)
    actions = []

    def callback(name):
        assert not fake.dispatching
        actions.append(name)
        if name == "exit":
            # The supervisor has accepted shutdown; only it closes the tray.
            icon.stop()

    icon = tray.WindowsTray(lambda: callback("open"), lambda: callback("exit"))
    icon.run()
    assert actions == ["open", "open", "exit"]
    assert ("menu_item", tray.MENU_OPEN, "打开 Lumen") in fake.calls
    assert ("menu_item", tray.MENU_EXIT, "退出 Lumen") in fake.calls
    assert fake.calls.count(("destroy_menu",)) == 2
    assert fake.calls.count(("notify", tray.NIM_DELETE)) == 1
    assert fake.calls.index(("notify", tray.NIM_DELETE)) < fake.calls.index(("destroy_window",))
    assert ("unregister",) in fake.calls
    assert not any(call[0] == "destroy_icon" for call in fake.calls), "stock shared icons are not owned"


def test_cancelling_exit_keeps_the_icon_and_accepts_later_open_actions(monkeypatch):
    fake = FakeWin32([
        (tray.WM_COMMAND, tray.MENU_EXIT, 0),
        (tray.WM_COMMAND, tray.MENU_OPEN, 0),
        (tray.WM_CLOSE, 0, 0),
    ])
    native(monkeypatch, fake)
    actions = []
    tray.WindowsTray(lambda: actions.append("open"), lambda: actions.append("exit requested")).run()
    assert actions == ["exit requested", "open"]
    assert ("post", tray.WM_CLOSE) not in fake.calls, "only the supervisor may commit shutdown"
    assert fake.calls.count(("notify", tray.NIM_DELETE)) == 1


@pytest.mark.parametrize('notification',[tray.WM_RBUTTONUP,tray.WM_CONTEXTMENU])
def test_dismissing_popup_with_stale_win32_error_keeps_tray_usable(monkeypatch,notification):
    fake=FakeWin32([
        (tray.WM_TRAYICON,0,notification|(1<<16)),
        (tray.WM_COMMAND,tray.MENU_OPEN,0),
        (tray.WM_TRAYICON,0,notification|(1<<16)),
        (tray.WM_CLOSE,0,0),
    ])
    native(monkeypatch,fake);monkeypatch.setattr(tray,'_last_error',lambda:1400)
    actions=[]
    tray.WindowsTray(lambda:actions.append('open'),lambda:actions.append('exit')).run()
    assert actions==['open'] and fake.calls.count(('popup',))==2
    assert fake.calls.count(('destroy_menu',))==2
    assert fake.calls.count(('notify',tray.NIM_DELETE))==1


def test_reentrant_context_notification_opens_only_one_popup(monkeypatch):
    fake=FakeWin32([(tray.WM_TRAYICON,0,tray.WM_CONTEXTMENU|(1<<16)),(tray.WM_CLOSE,0,0)])
    native(monkeypatch,fake);popups=[];actions=[]
    def popup(*args):
        popups.append(True)
        if len(popups)==1:
            fake.proc(fake.hwnd,tray.WM_TRAYICON,0,tray.WM_CONTEXTMENU|(1<<16))
            return tray.MENU_OPEN
        return 0
    monkeypatch.setattr(fake,'TrackPopupMenu',popup)
    tray.WindowsTray(lambda:actions.append('open'),lambda:actions.append('exit')).run()
    assert len(popups)==1 and actions==['open']


def test_transient_popup_failure_keeps_icon_and_later_open_available(monkeypatch,caplog):
    fake=FakeWin32([
        (tray.WM_TRAYICON,0,tray.WM_CONTEXTMENU|(1<<16)),
        (tray.WM_TRAYICON,0,tray.WM_LBUTTONDBLCLK|(1<<16)),
        (tray.WM_TRAYICON,0,tray.WM_CONTEXTMENU|(1<<16)),
        (tray.WM_CLOSE,0,0),
    ])
    native(monkeypatch,fake);created=[];actions=[]
    def create_menu():
        created.append(True);return 0 if len(created)==1 else fake.menu
    monkeypatch.setattr(fake,'CreatePopupMenu',create_menu)
    tray.WindowsTray(lambda:actions.append('open'),lambda:actions.append('exit')).run()
    assert actions==['open'] and len(created)==2
    assert fake.calls.count(('notify',tray.NIM_ADD))==1
    assert 'CreatePopupMenu' in caplog.text


def test_explorer_restart_readds_the_icon_and_sets_its_version(monkeypatch):
    fake = FakeWin32([(0xC123, 0, 0), (tray.WM_CLOSE, 0, 0)])
    native(monkeypatch, fake)
    tray.WindowsTray(lambda: None, lambda: None).run()
    assert fake.calls.count(("notify", tray.NIM_ADD)) == 2
    assert fake.calls.count(("notify", tray.NIM_SETVERSION)) == 2
    assert fake.calls.count(("notify", tray.NIM_DELETE)) == 1


def test_callback_failure_still_deletes_icon_window_owned_icon_and_class(monkeypatch, tmp_path):
    fake = FakeWin32([(tray.WM_COMMAND, tray.MENU_OPEN, 0)])
    native(monkeypatch, fake)

    def fail():
        raise RuntimeError("supervisor queue unavailable")

    with pytest.raises(RuntimeError, match="supervisor queue"):
        tray.WindowsTray(fail, lambda: None, tmp_path / "lumen.ico").run()
    for expected in [("notify", tray.NIM_DELETE), ("destroy_window",), ("destroy_icon",), ("unregister",)]:
        assert expected in fake.calls


def test_native_callback_failure_is_raised_after_dispatch_instead_of_swallowed(monkeypatch):
    fake = FakeWin32([(0xC123, 0, 0)])
    fake.fail_add_at = 2
    native(monkeypatch, fake)
    with pytest.raises(OSError, match="NIM_ADD"):
        tray.WindowsTray(lambda: None, lambda: None).run()
    assert ("notify", tray.NIM_DELETE) in fake.calls
    assert ("destroy_window",) in fake.calls
    assert ("unregister",) in fake.calls


def test_get_message_failure_cleans_up(monkeypatch):
    fake = FakeWin32()
    fake.fail_get_message = True
    native(monkeypatch, fake)
    with pytest.raises(OSError, match="GetMessageW"):
        tray.WindowsTray(lambda: None, lambda: None).run()
    assert ("notify", tray.NIM_DELETE) in fake.calls
    assert ("destroy_window",) in fake.calls


def test_stop_wakes_a_blocked_message_loop_from_another_thread(monkeypatch):
    fake = FakeWin32()
    native(monkeypatch, fake)
    icon = tray.WindowsTray(lambda: None, lambda: None)
    failures = []

    def run():
        try:
            icon.run()
        except BaseException as failure:
            failures.append(failure)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert fake.waiting.wait(2)
        icon.stop()
        worker.join(2)
        assert not worker.is_alive()
        assert not failures
        assert ("notify", tray.NIM_DELETE) in fake.calls
    finally:
        icon.stop()
        worker.join(4)


def test_stop_before_start_allocates_no_win32_resources_and_run_is_one_shot(monkeypatch):
    monkeypatch.setattr(tray.sys, "platform", "win32")
    monkeypatch.setattr(tray, "_Win32", lambda: pytest.fail("stop-before-run must not load native DLLs"))
    icon = tray.WindowsTray(lambda: None, lambda: None)
    icon.stop()
    icon.run()
    with pytest.raises(RuntimeError, match="once"):
        icon.run()


def test_native_abi_and_signature_widths_are_explicit(monkeypatch):
    assert ctypes.sizeof(tray.DWORD) == 4
    assert ctypes.sizeof(tray.WPARAM) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(tray.LPARAM) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(tray.LRESULT) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(tray.NOTIFYICONDATAW) == (976 if ctypes.sizeof(ctypes.c_void_p) == 8 else 956)
    assert ctypes.sizeof(tray.WNDCLASSW) == (72 if ctypes.sizeof(ctypes.c_void_p) == 8 else 40)

    class Function:
        def __call__(self, *args):
            return 1

    class DLL:
        def __getattr__(self, name):
            function = Function()
            setattr(self, name, function)
            return function

    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: DLL(), raising=False)
    api = tray._Win32()
    assert api.CreateWindowExW.restype is tray.HWND
    assert api.CreatePopupMenu.restype is tray.HMENU
    assert api.DefWindowProcW.restype is tray.LRESULT
    assert api.DefWindowProcW.argtypes == [tray.HWND, tray.UINT, tray.WPARAM, tray.LPARAM]
    assert api.AppendMenuW.argtypes[2] is tray.UINT_PTR
    assert api.DispatchMessageW.restype is tray.LRESULT


def test_non_windows_is_explicit_and_module_imports_no_gui_toolkit(monkeypatch):
    monkeypatch.setattr(tray.sys, "platform", "linux")
    with pytest.raises(OSError, match="requires Windows"):
        tray.WindowsTray(lambda: None, lambda: None)
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    subprocess.run([sys.executable, "-c", "import sys; import lumen.windows_tray; assert not any(name.startswith(('PySide6', 'PIL', 'win32gui')) for name in sys.modules)"], env=environment, check=True)
