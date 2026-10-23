"""Windows shell integration for a borderless, monitor-sized player window."""
import ctypes
import sys
import uuid
from ctypes import wintypes


class GUID(ctypes.Structure):
    _fields_ = [('data', ctypes.c_ubyte * 16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _mark_fullscreen(hwnd, enabled):
    # ITaskbarList2::MarkFullscreenWindow tells Explorer to put its taskbar
    # behind this window. Never hide the global taskbar or make the player
    # permanently topmost (Alt+Tab must still work).
    ole32 = ctypes.WinDLL('ole32')
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    # Qt may already have initialized COM using a different apartment model.
    initialized = ole32.CoInitializeEx(None, 2) in (0, 1)
    interface = ctypes.c_void_p()
    try:
        clsid = GUID.parse('56FDF344-FD6D-11D0-958A-006097C9A090')
        iid = GUID.parse('602D4995-B13A-429B-A66E-1935E44F4317')
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(interface)) < 0:
            return
        table = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(table[2])
        try:
            initialize = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(table[3])
            mark = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, wintypes.BOOL)(table[8])
            if initialize(interface) >= 0:
                mark(interface, hwnd, enabled)
        finally:
            release(interface)
    finally:
        if initialized:
            ole32.CoUninitialize()


def set_fullscreen_window(window_id, enabled):
    if sys.platform != 'win32':
        return
    hwnd = wintypes.HWND(int(window_id))
    try:
        _mark_fullscreen(hwnd, enabled)
    except OSError:
        # Explorer may be unavailable; Qt's borderless fullscreen still works.
        pass
    if not enabled:
        return
    # Native coordinates are physical pixels. QScreen geometry is in logical
    # pixels, which cannot be passed directly to SetWindowPos on mixed-DPI PCs.
    class MonitorInfo(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                    ('work', wintypes.RECT), ('flags', wintypes.DWORD)]

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        rect = info.monitor
        current=wintypes.RECT()
        if user32.GetWindowRect(hwnd,ctypes.byref(current)) and (current.left,current.top,current.right,current.bottom)==(rect.left,rect.top,rect.right,rect.bottom):return
        # Qt already removed the frame. FRAMECHANGED needlessly invalidates the
        # surface on each queued fullscreen event and can expose a black frame.
        user32.SetWindowPos(hwnd, None, rect.left, rect.top, rect.right - rect.left,
                            rect.bottom - rect.top, 0x0010 | 0x0200)  # NOACTIVATE | NOOWNERZORDER
