"""Native Windows notification-area icon, with no GUI toolkit dependency.

``run`` owns its calling thread's Win32 message loop. Callbacks run after native
message dispatch, never inside WNDPROC; supply short callbacks that enqueue work
for the application's supervisor. ``stop`` may be called from another thread.
"""
from __future__ import annotations

from collections import deque
import ctypes
import logging
from pathlib import Path
import sys
import threading
from typing import Callable

# Windows integer widths must not follow the host's C ``long`` (64-bit on Linux).
BOOL = ctypes.c_int32
DWORD = UINT = ctypes.c_uint32
WORD = ctypes.c_uint16
LONG = ctypes.c_int32
HANDLE = HWND = HINSTANCE = HICON = HCURSOR = HBRUSH = HMENU = ctypes.c_void_p
WPARAM = UINT_PTR = ctypes.c_size_t
LPARAM = LRESULT = ctypes.c_ssize_t
LPCWSTR = ctypes.c_wchar_p
_WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
WNDPROC = _WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", HWND), ("message", UINT), ("wParam", WPARAM),
        ("lParam", LPARAM), ("time", DWORD), ("pt", POINT),
        ("lPrivate", DWORD),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE), ("hIcon", HICON), ("hCursor", HCURSOR),
        ("hbrBackground", HBRUSH), ("lpszMenuName", LPCWSTR),
        ("lpszClassName", LPCWSTR),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", DWORD), ("Data2", WORD), ("Data3", WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _TimeoutOrVersion(ctypes.Union):
    _fields_ = [("uTimeout", UINT), ("uVersion", UINT)]


class NOTIFYICONDATAW(ctypes.Structure):
    # UTF-16 code units keep the ABI inspectable on non-Windows test hosts too.
    _anonymous_ = ("timeout_or_version",)
    _fields_ = [
        ("cbSize", DWORD), ("hWnd", HWND), ("uID", UINT), ("uFlags", UINT),
        ("uCallbackMessage", UINT), ("hIcon", HICON), ("szTip", WORD * 128),
        ("dwState", DWORD), ("dwStateMask", DWORD), ("szInfo", WORD * 256),
        ("timeout_or_version", _TimeoutOrVersion), ("szInfoTitle", WORD * 64),
        ("dwInfoFlags", DWORD), ("guidItem", GUID), ("hBalloonIcon", HICON),
    ]


WM_NULL = 0
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_CONTEXTMENU = 0x007B
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_ACTIONS = WM_APP + 2
NIN_KEYSELECT = 0x0401
NIM_ADD, NIM_DELETE, NIM_SETVERSION = 0, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
NIF_SHOWTIP = 0x0080
NOTIFYICON_VERSION_4 = 4
MENU_OPEN, MENU_EXIT = 1001, 1002
ERROR_INVALID_WINDOW_HANDLE = 1400


def _last_error() -> int:
    reader = getattr(ctypes, "get_last_error", None)
    return reader() if reader else 0


def _failure(operation: str) -> OSError:
    code = _last_error()
    return OSError(code, f"{operation} failed" if not code else f"{operation} failed (Win32 {code})")


class _Win32:
    """All pointer/handle-returning APIs have explicit 32/64-bit signatures."""

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        bindings = [
            (self.kernel32, "GetModuleHandleW", [LPCWSTR], HINSTANCE),
            (self.user32, "RegisterClassW", [ctypes.POINTER(WNDCLASSW)], WORD),
            (self.user32, "UnregisterClassW", [LPCWSTR, HINSTANCE], BOOL),
            (self.user32, "RegisterWindowMessageW", [LPCWSTR], UINT),
            (self.user32, "CreateWindowExW", [DWORD, LPCWSTR, LPCWSTR, DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                HWND, HMENU, HINSTANCE, ctypes.c_void_p], HWND),
            (self.user32, "DefWindowProcW", [HWND, UINT, WPARAM, LPARAM], LRESULT),
            (self.user32, "DestroyWindow", [HWND], BOOL),
            (self.user32, "GetMessageW", [ctypes.POINTER(MSG), HWND, UINT, UINT], BOOL),
            (self.user32, "TranslateMessage", [ctypes.POINTER(MSG)], BOOL),
            (self.user32, "DispatchMessageW", [ctypes.POINTER(MSG)], LRESULT),
            (self.user32, "PostMessageW", [HWND, UINT, WPARAM, LPARAM], BOOL),
            (self.user32, "PostQuitMessage", [ctypes.c_int], None),
            (self.user32, "LoadIconW", [HINSTANCE, LPCWSTR], HICON),
            (self.user32, "LoadImageW", [HINSTANCE, LPCWSTR, UINT,
                ctypes.c_int, ctypes.c_int, UINT], HANDLE),
            (self.user32, "DestroyIcon", [HICON], BOOL),
            (self.user32, "CreatePopupMenu", [], HMENU),
            (self.user32, "AppendMenuW", [HMENU, UINT, UINT_PTR, LPCWSTR], BOOL),
            (self.user32, "GetCursorPos", [ctypes.POINTER(POINT)], BOOL),
            (self.user32, "SetForegroundWindow", [HWND], BOOL),
            (self.user32, "TrackPopupMenu", [HMENU, UINT, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, HWND, ctypes.c_void_p], UINT),
            (self.user32, "DestroyMenu", [HMENU], BOOL),
            (self.shell32, "Shell_NotifyIconW", [DWORD, ctypes.POINTER(NOTIFYICONDATAW)], BOOL),
        ]
        for library, name, arguments, result in bindings:
            function = getattr(library, name)
            function.argtypes = arguments
            function.restype = result
            setattr(self, name, function)


class WindowsTray:
    """One native tray/message-loop lifetime; callbacks should enqueue app work."""

    def __init__(
        self, on_open: Callable[[], None], on_exit: Callable[[], None],
        icon_path: str | Path | None = None,
    ) -> None:
        if sys.platform != "win32":
            raise OSError("The native notification-area icon requires Windows")
        self._on_open, self._on_exit = on_open, on_exit
        self._icon_path = Path(icon_path) if icon_path is not None else None
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._has_run = False
        self._api: _Win32 | None = None
        self._hwnd: int | None = None
        self._wndproc: WNDPROC | None = None
        self._callback_error: BaseException | None = None
        self._actions: deque[Callable[[], None]] = deque()
        self._taskbar_created = 0
        self._icon_data: NOTIFYICONDATAW | None = None
        self._icon_added = False
        self._menu_pending = False

    def stop(self) -> None:
        """Wake and close the loop from any thread, including before startup."""
        self._stop_requested.set()
        with self._lock:
            api, hwnd = self._api, self._hwnd
        if api is not None and hwnd and not api.PostMessageW(hwnd, WM_CLOSE, 0, 0):
            if _last_error() != ERROR_INVALID_WINDOW_HANDLE:
                raise _failure("PostMessageW(WM_CLOSE)")

    def _queue(self, action: Callable[[], None]) -> None:
        self._actions.append(action)
        if not self._api.PostMessageW(self._hwnd, WM_ACTIONS, 0, 0):
            raise _failure("PostMessageW(WM_ACTIONS)")

    def _drain_actions(self) -> None:
        while self._actions:
            self._actions.popleft()()

    def _add_icon(self) -> None:
        if not self._api.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._icon_data)):
            raise _failure("Shell_NotifyIconW(NIM_ADD)")
        self._icon_added = True
        self._icon_data.uVersion = NOTIFYICON_VERSION_4
        if not self._api.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(self._icon_data)):
            raise _failure("Shell_NotifyIconW(NIM_SETVERSION)")

    def _dispatch_menu(self, command: int) -> None:
        if command == MENU_OPEN:
            self._queue(self._on_open)
        elif command == MENU_EXIT:
            self._queue(self._on_exit)

    def _request_menu(self) -> None:
        # TrackPopupMenu pumps messages itself. Defer the popup outside WNDPROC
        # and coalesce duplicate/reentrant Shell context notifications.
        if self._menu_pending or self._stop_requested.is_set():
            return
        self._menu_pending = True
        self._queue(self._show_menu)

    def _show_menu(self) -> None:
        try:
            if not self._stop_requested.is_set():
                self._menu(self._hwnd)
        except OSError:
            # A transient menu error must not stop LAN/watching or remove the
            # tray. Startup/registration failures retain their fatal handling.
            logging.getLogger(__name__).warning('Cannot open Windows tray menu',exc_info=True)
        finally:
            self._menu_pending = False

    def _menu(self, hwnd: int) -> None:
        api = self._api
        menu = api.CreatePopupMenu()
        if not menu:
            raise _failure("CreatePopupMenu")
        try:
            if not api.AppendMenuW(menu, 0, MENU_OPEN, "打开 Lumen"):
                raise _failure("AppendMenuW(open)")
            if not api.AppendMenuW(menu, 0x0800, 0, None):
                raise _failure("AppendMenuW(separator)")
            if not api.AppendMenuW(menu, 0, MENU_EXIT, "退出 Lumen"):
                raise _failure("AppendMenuW(exit)")
            point = POINT()
            if not api.GetCursorPos(ctypes.byref(point)):
                raise _failure("GetCursorPos")
            # Windows may deny foreground activation; the menu still works.
            api.SetForegroundWindow(hwnd)
            command = api.TrackPopupMenu(menu, 0x0100 | 0x0080 | 0x0002,
                point.x, point.y, 0, hwnd, None)
            # With TPM_RETURNCMD zero also means normal dismissal. The nested
            # message loop may leave an unrelated LastError even on cancellation.
            if command and not self._stop_requested.is_set():
                self._dispatch_menu(command)
        finally:
            api.DestroyMenu(menu)
            # Required by Shell's popup-menu dismissal behavior.
            api.PostMessageW(hwnd, WM_NULL, 0, 0)

    def _window_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        api = self._api
        if message == self._taskbar_created:
            if self._icon_data is not None:
                self._add_icon()
            return 0
        if message == WM_TRAYICON:
            event = lparam & 0xFFFF  # Works with NOTIFYICON_VERSION_4 packing.
            if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._request_menu()
            elif event in (WM_LBUTTONDBLCLK, NIN_KEYSELECT):
                self._queue(self._on_open)
            return 0
        if message == WM_COMMAND:
            self._dispatch_menu(wparam & 0xFFFF)
            return 0
        if message == WM_ACTIONS:
            return 0
        if message == WM_CLOSE:
            # Keep HWND valid until finally removes its Shell icon.
            api.PostQuitMessage(0)
            return 0
        if message == WM_DESTROY:
            with self._lock:
                self._hwnd = None
            api.PostQuitMessage(0)
            return 0
        return api.DefWindowProcW(hwnd, message, wparam, lparam)

    def _native_window_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        # Exceptions must not escape a ctypes callback: ctypes otherwise discards them.
        try:
            return self._window_proc(hwnd, message, wparam, lparam)
        except BaseException as failure:
            self._callback_error = failure
            if self._api is not None:
                self._api.PostQuitMessage(1)
            return 0

    def run(self) -> None:
        """Run on the tray thread; report startup/dispatch errors to its caller."""
        with self._lock:
            if self._has_run:
                raise RuntimeError("WindowsTray.run() may only be called once")
            self._has_run = True
        if self._stop_requested.is_set():
            return
        api = _Win32()
        with self._lock:
            self._api = api
        instance = icon = None
        atom = 0
        owned_icon = False
        class_name = f"Lumen.NativeTray.{id(self):x}"
        try:
            instance = api.GetModuleHandleW(None)
            if not instance:
                raise _failure("GetModuleHandleW")
            self._taskbar_created = api.RegisterWindowMessageW("TaskbarCreated")
            if not self._taskbar_created:
                raise _failure("RegisterWindowMessageW(TaskbarCreated)")
            if self._icon_path is None:
                icon = api.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), LPCWSTR))
            else:
                icon = api.LoadImageW(None, str(self._icon_path), 1, 0, 0, 0x0010 | 0x0040)
                owned_icon = True
            if not icon:
                raise _failure("LoadImageW" if owned_icon else "LoadIconW")
            self._wndproc = WNDPROC(self._native_window_proc)
            window_class = WNDCLASSW()
            window_class.style = 0x0008  # CS_DBLCLKS
            window_class.lpfnWndProc = self._wndproc
            window_class.hInstance, window_class.hIcon = instance, icon
            window_class.lpszClassName = class_name
            atom = api.RegisterClassW(ctypes.byref(window_class))
            if not atom:
                raise _failure("RegisterClassW")
            # Hidden top-level windows receive Explorer's TaskbarCreated broadcast;
            # message-only HWND_MESSAGE windows do not.
            hwnd = api.CreateWindowExW(0, class_name, "Lumen background", 0,
                0, 0, 0, 0, None, None, instance, None)
            if not hwnd:
                raise _failure("CreateWindowExW")
            with self._lock:
                self._hwnd = hwnd
            if self._stop_requested.is_set():
                return
            data = NOTIFYICONDATAW()
            data.cbSize, data.hWnd, data.uID = ctypes.sizeof(data), hwnd, 1
            data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
            data.uCallbackMessage, data.hIcon = WM_TRAYICON, icon
            tip = "Lumen".encode("utf-16-le")
            for index in range(0, len(tip), 2):
                data.szTip[index // 2] = int.from_bytes(tip[index:index + 2], "little")
            self._icon_data = data
            self._add_icon()
            message = MSG()
            while True:
                result = api.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise _failure("GetMessageW")
                if result == 0:
                    break
                api.TranslateMessage(ctypes.byref(message))
                api.DispatchMessageW(ctypes.byref(message))
                if self._callback_error is not None:
                    raise self._callback_error
                self._drain_actions()
            if self._callback_error is not None:
                raise self._callback_error
        finally:
            active_error = sys.exception()
            cleanup_error = None

            def clean(action):
                nonlocal cleanup_error
                try:
                    action()
                except BaseException as failure:
                    if cleanup_error is None:
                        cleanup_error = failure

            if self._icon_added and self._icon_data is not None:
                clean(lambda: api.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._icon_data)))
                self._icon_added = False
            with self._lock:
                hwnd = self._hwnd
            if hwnd:
                clean(lambda: api.DestroyWindow(hwnd))
            if owned_icon and icon:
                clean(lambda: api.DestroyIcon(icon))
            if atom:
                clean(lambda: api.UnregisterClassW(class_name, instance))
            with self._lock:
                self._hwnd, self._api = None, None
            self._wndproc = None
            if cleanup_error is not None and active_error is None:
                raise cleanup_error
