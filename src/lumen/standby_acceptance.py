"""Windows frozen-owner acceptance; never substitutes for native tray checks."""
from datetime import datetime, timezone
import ctypes
import hashlib
import json
import ntpath
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import zlib


TARGET_BYTES = 50_000_000


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_uint32), ('PageFaultCount', ctypes.c_uint32)] + [
        (name, ctypes.c_size_t) for name in (
            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
            'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage',
            'PeakPagefileUsage', 'PrivateUsage')]


def _windows_libraries():
    return ctypes.WinDLL('kernel32', use_last_error=True), ctypes.WinDLL('psapi', use_last_error=True)


def _gui_module(name):
    name = ntpath.basename(name).casefold()
    return (name.startswith('qt6') and name.endswith('.dll') or
            name.startswith(('qtcore', 'qtgui', 'qtwidgets')) and name.endswith('.pyd') or
            name.startswith(('libmpv', 'mpv-')) and name.endswith('.dll') or name == 'mpv.dll')


def windows_process_memory(pid):
    """Read an owned x64 process using PSAPI; failed/partial reads are errors."""
    if sys.platform != 'win32':
        raise OSError('Windows PSAPI measurement requires Windows')
    kernel, psapi = _windows_libraries()
    handle_type, dword = ctypes.c_void_p, ctypes.c_uint32
    kernel.OpenProcess.argtypes = [dword, ctypes.c_int32, dword]
    kernel.OpenProcess.restype = handle_type
    kernel.CloseHandle.argtypes = [handle_type]
    kernel.CloseHandle.restype = ctypes.c_int32
    psapi.GetProcessMemoryInfo.argtypes = [handle_type, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), dword]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int32
    psapi.EnumProcessModulesEx.argtypes = [handle_type, ctypes.POINTER(handle_type), dword,
                                        ctypes.POINTER(dword), dword]
    psapi.EnumProcessModulesEx.restype = ctypes.c_int32
    psapi.GetModuleFileNameExW.argtypes = [handle_type, handle_type, ctypes.c_wchar_p, dword]
    psapi.GetModuleFileNameExW.restype = dword
    process = kernel.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ
    if not process:
        raise OSError('Cannot open standby process for PSAPI measurement')
    try:
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            raise OSError('Cannot read standby process memory')
        if not counters.WorkingSetSize or not counters.PrivateUsage:
            raise OSError('Standby process memory counters are empty')
        count = 256
        while True:
            modules = (handle_type * count)()
            needed = dword()
            if not psapi.EnumProcessModulesEx(process, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3):
                raise OSError('Cannot enumerate standby process modules')
            if needed.value <= ctypes.sizeof(modules):
                break
            count = (needed.value + ctypes.sizeof(handle_type) - 1) // ctypes.sizeof(handle_type)
            if count > 4096:
                raise OSError('Standby process module list exceeds acceptance limit')
        if not needed.value or needed.value % ctypes.sizeof(handle_type):
            raise OSError('Standby process module list is empty or incomplete')
        names = []
        for module in modules[:needed.value // ctypes.sizeof(handle_type)]:
            buffer = ctypes.create_unicode_buffer(32768)
            length = psapi.GetModuleFileNameExW(process, module, buffer, len(buffer))
            if not length or length >= len(buffer):
                raise OSError('Cannot read a standby process module name')
            names.append(ntpath.basename(buffer.value))
        return {'working_set_bytes': counters.WorkingSetSize, 'private_usage_bytes': counters.PrivateUsage,
                'module_count': len(names), 'gui_modules': sorted(name for name in names if _gui_module(name))}
    finally:
        kernel.CloseHandle(process)


def _command(executable, arguments):
    return [str(executable), *arguments]


def _wait(function, timeout, description):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = function()
        if value:
            return value
        time.sleep(.05)
    raise RuntimeError('Standby acceptance timed out: ' + description)


def _poster():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 2, 3, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress((b'\0' + b'\x20\x80\xa0' * 2) * 3)) + chunk(b'IEND', b''))


def _stop(process, client):
    if process.poll() is not None:
        return
    try:
        if client:
            client.request('exit')
        process.wait(timeout=10)
    except Exception:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def verify_standby(executable, *, timeout=30):
    """Check one exact EXE in disposable data; return persistable public proof.

    The 50 MB target is recorded, not enforced by trimming or memory limits.
    DLL isolation, IPC, LAN, worker routing and clean shutdown are hard gates.
    """
    from .core import Library
    from .desktop_runtime import RuntimeClient

    executable = Path(executable).resolve(strict=True)
    started = time.time()
    proof = {'format_version': 1, 'status': 'pending', 'started_epoch': started,
             'verified_at': datetime.now(timezone.utc).isoformat(), 'platform': sys.platform,
             'entry': 'Lumen.exe --background-no-tray --data-dir <isolated synthetic library>',
             'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
             'tray': False, 'native_tray_manual_acceptance': 'unverified',
             'target_bytes': TARGET_BYTES, 'measurement': 'Windows PSAPI WorkingSetSize and PrivateUsage, bytes',
             'limitations': ['No-tray CI entry; native tray icon/menu and Windows login remain manual checks.',
                             'Idle owner only; GUI/playback and active worker descendants are outside samples.',
                             'Memory varies by Windows build, security software and library size; no trimming is used.'],
             'samples': [], 'checks': {}}
    with tempfile.TemporaryDirectory(prefix='lumen-standby-') as temporary:
        root = Path(temporary)
        directory = root / 'Data with spaces'
        content = bytes(range(256)) * 8192
        media = root / 'Synthetic.mp4'; media.write_bytes(content)
        image = _poster()
        library = Library(directory)
        poster = directory / 'cache' / 'synthetic-poster.png'; poster.write_bytes(image)
        token = secrets.token_hex(32)
        try:
            with library.db:
                work_id = library.db.execute(
                    'INSERT INTO works(identity,kind,title,added,metadata,thumbnail) VALUES(?,?,?,?,?,?)',
                    ('standby-acceptance', 'movie', 'Synthetic', '2026-11-11', '{"nfo_poster":true}', str(poster))).lastrowid
                file_id = library.db.execute(
                    'INSERT INTO files(work_id,path,root,digest,duration) VALUES(?,?,?,?,?)',
                    (work_id, str(media), str(root), 'standby-acceptance', 100)).lastrowid
            library.set_setting('lan', {'enabled': True, 'port': 0})
            library.set_setting('lan_token', token)
        finally:
            library.close()
        environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
        environment.pop('LUMEN_BACKGROUND_SERVICE', None)
        environment.pop('LUMEN_IMAGE_WORKER', None)
        arguments = ['--background-no-tray', '--data-dir', str(directory)]
        process = subprocess.Popen(_command(executable, arguments), env=environment,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = None
        try:
            def connected():
                if process.poll() is not None:
                    raise RuntimeError('Packaged standby owner exited before IPC was ready')
                try:
                    candidate = RuntimeClient(directory, timeout=3)
                    state = candidate.request('status')
                    return candidate if state['lan']['running'] and not state['gui_running'] else None
                except (OSError, ValueError):
                    return None
            client = _wait(connected, timeout, 'owner IPC/LAN startup')
            if client.pid != process.pid:
                raise RuntimeError('Standby IPC PID does not belong to the launched executable')
            proof['checks']['ipc_owner_identity'] = True

            def sample(stage):
                state = client.request('status')
                if state['gui_running'] or state['worker']['running']:
                    raise RuntimeError('Idle sample unexpectedly contains an active GUI/background task')
                result = windows_process_memory(process.pid)
                if result['gui_modules']:
                    raise RuntimeError('Standby owner loaded GUI/playback modules: ' + ', '.join(result['gui_modules']))
                proof['samples'].append({'stage': stage, **result})
            for _ in range(3):
                sample('cold_idle')
                time.sleep(.15)

            opener = build_opener(ProxyHandler({}))
            port = client.request('status')['lan']['port']
            base = f'http://127.0.0.1:{port}'
            def get(route, *, headers=None):
                request = Request(base + route, headers={'Authorization': 'Bearer ' + token, **(headers or {})})
                with opener.open(request, timeout=timeout) as response:
                    return response.status, dict(response.headers), response.read()
            try:
                opener.open(Request(base + '/api/info'), timeout=3)
            except HTTPError as error:
                if error.code not in (401, 403):
                    raise
            else:
                raise RuntimeError('Standby LAN accepted an unauthenticated request')
            if get('/api/info')[0] != 200:
                raise RuntimeError('Standby LAN info failed')
            if not any(work['id'] == work_id for work in json.loads(get('/api/works')[2])['items']):
                raise RuntimeError('Standby LAN catalog omitted the synthetic work')
            status, headers, body = get(f'/api/files/{file_id}/stream', headers={'Range': 'bytes=123-1022'})
            if status != 206 or body != content[123:1023] or headers.get('Content-Range') != f'bytes 123-1022/{len(content)}':
                raise RuntimeError('Standby LAN Range response changed bytes or bounds')
            if get(f'/api/works/{work_id}/cover')[2] != image:
                raise RuntimeError('Standby LAN isolated cover returned different bytes')
            proof['checks'].update(lan_authentication=True, lan_catalog=True, lan_range=True, isolated_cover=True)
            sample('after_lan_and_cover')

            channel = root / 'image-channel'; channel.mkdir(mode=0o700)
            request, response = channel / 'request.json', channel / 'response.json'
            details = poster.stat()
            request.write_text(json.dumps({'op': 'dimensions', 'path': str(poster),
                                           'modified': details.st_mtime_ns, 'size': details.st_size}), encoding='utf-8')
            request.chmod(0o600)
            subprocess.run(_command(executable, ['--image-worker', '--request', str(request), '--response', str(response)]),
                           check=True, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout)
            if json.loads(response.read_text(encoding='utf-8')) != {'ok': True, 'result': [2, 3]}:
                raise RuntimeError('Packaged image-worker entry did not decode the synthetic poster')
            result = root / 'worker-result.json'
            subprocess.run(_command(executable, ['--background-worker', 'watch', '--data-dir', str(directory),
                                                 '--result-file', str(result)]),
                           check=True, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout)
            worker = json.loads(result.read_text(encoding='utf-8'))
            if worker.get('job') != 'watch' or worker.get('status') != 'done':
                raise RuntimeError('Packaged background-worker entry did not finish its marker result')
            proof['checks'].update(image_worker_entry=True, background_worker_entry=True)

            subprocess.run(_command(executable, arguments), check=True, env=environment, timeout=timeout,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            duplicate = RuntimeClient(directory, timeout=3)
            if duplicate.pid != process.pid or duplicate.request('status')['gui_running']:
                raise RuntimeError('Duplicate background invocation replaced the owner or opened a GUI')
            proof['checks']['single_instance'] = True
            library = Library(directory, initialize=False)
            try:
                if library.setting('lan') != {'enabled': True, 'port': 0}:
                    raise RuntimeError('Standby launch changed the persisted LAN configuration')
            finally:
                library.close()
            proof['checks']['lan_configuration_preserved'] = True
            for _ in range(3):
                sample('final_idle')
                time.sleep(.15)
            client.request('exit')
            process.wait(timeout=timeout)
            if process.returncode or (directory / 'desktop-runtime.json').exists():
                raise RuntimeError('Standby exit failed or left stale runtime metadata')
            for closed_port in (port, client.port):
                try:
                    connection = socket.create_connection(('127.0.0.1', closed_port), timeout=2)
                except ConnectionRefusedError:
                    pass
                else:
                    connection.close()
                    raise RuntimeError('Standby LAN/control listener remained active after exit')
            proof['checks']['clean_exit'] = True
        finally:
            _stop(process, client)
    proof['max_working_set_bytes'] = max(sample['working_set_bytes'] for sample in proof['samples'])
    proof['max_private_usage_bytes'] = max(sample['private_usage_bytes'] for sample in proof['samples'])
    proof['working_set_target_met'] = proof['max_working_set_bytes'] < TARGET_BYTES
    proof['cold_working_set_target_met'] = max(sample['working_set_bytes'] for sample in proof['samples']
                                               if sample['stage'] == 'cold_idle') < TARGET_BYTES
    proof['status'] = 'passed'
    return proof


def write_report(path, proof):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
