"""Resource caps for the trusted JavaScript runner process (not exposed to scripts)."""
import os

_job_handle = None


def limit_worker():
    memory = 768 * 1024 * 1024
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (7, 7))
        return
    import ctypes
    from ctypes import wintypes
    size_t = ctypes.c_size_t
    class BASIC(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', size_t), ('MaximumWorkingSetSize', size_t),
                    ('ActiveProcessLimit', wintypes.DWORD), ('Affinity', size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
    class EXTENDED(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO), ('ProcessMemoryLimit', size_t), ('JobMemoryLimit', size_t), ('PeakProcessMemoryUsed', size_t), ('PeakJobMemoryUsed', size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    global _job_handle
    _job_handle = kernel.CreateJobObjectW(None, None)
    if not _job_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x100 | 0x2000  # PROCESS_MEMORY | KILL_ON_JOB_CLOSE
    info.ProcessMemoryLimit = memory
    if not kernel.SetInformationJobObject(_job_handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(_job_handle, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
