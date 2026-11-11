import ctypes
import json
import os
from pathlib import Path
import site
import socket
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

from lumen import standby_acceptance as acceptance


class Function:
    def __init__(self, function):
        self.function = function

    def __call__(self, *arguments):
        return self.function(*arguments)


class WindowsAPI:
    def __init__(self, names=None, fail=None):
        self.names = names or [r'C:\Python\python312.dll', r'C:\Windows\System32\kernel32.dll']
        self.fail = fail
        self.closed = []
        self.enum_calls = 0
        self.kernel = SimpleNamespace(OpenProcess=Function(self.open),
                                      CloseHandle=Function(lambda handle: self.closed.append(handle) or 1))
        self.psapi = SimpleNamespace(GetProcessMemoryInfo=Function(self.memory),
                                    EnumProcessModulesEx=Function(self.modules),
                                    GetModuleFileNameExW=Function(self.filename))

    def open(self, access, inherit, pid):
        assert access == 0x0410 and inherit is False and pid == 1234
        return None if self.fail == 'open' else 5678

    def memory(self, process, pointer, size):
        assert process == 5678 and size == ctypes.sizeof(acceptance.PROCESS_MEMORY_COUNTERS_EX)
        counters = ctypes.cast(pointer, ctypes.POINTER(acceptance.PROCESS_MEMORY_COUNTERS_EX)).contents
        assert counters.cb == size
        counters.WorkingSetSize = 49_999_999
        counters.PrivateUsage = 6_123_456_789  # exercise SIZE_T, not truncated DWORD
        if self.fail == 'empty-memory':
            counters.WorkingSetSize = 0
        return self.fail != 'memory'

    def modules(self, process, modules, size, pointer, flags):
        self.enum_calls += 1
        assert process == 5678 and flags == 3
        needed = (4097 if self.fail == 'limit' else len(self.names)) * ctypes.sizeof(ctypes.c_void_p)
        if self.fail == 'empty-modules':
            needed = 0
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = needed
        if needed <= size:
            for index in range(len(self.names)):
                modules[index] = index + 1
        return self.fail != 'modules'

    def filename(self, process, module, buffer, size):
        assert process == 5678 and size == 32768
        if self.fail == 'filename':
            return 0
        buffer.value = self.names[module - 1]
        return len(buffer.value)


def windows_api(monkeypatch, names=None, fail=None):
    api = WindowsAPI(names, fail)
    monkeypatch.setattr(acceptance, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(acceptance, '_windows_libraries', lambda: (api.kernel, api.psapi))
    return api


def test_psapi_reads_real_width_counters_and_closes_process_handle(monkeypatch):
    api = windows_api(monkeypatch)
    assert acceptance.windows_process_memory(1234) == {
        'working_set_bytes': 49_999_999, 'private_usage_bytes': 6_123_456_789,
        'module_count': 2, 'gui_modules': [],
    }
    assert api.closed == [5678]
    assert api.kernel.OpenProcess.restype is ctypes.c_void_p
    assert acceptance.PROCESS_MEMORY_COUNTERS_EX.WorkingSetSize.offset == 8 + ctypes.sizeof(ctypes.c_size_t)


def test_psapi_retries_a_larger_module_snapshot_and_detects_gui_dlls(monkeypatch):
    names = [rf'C:\Windows\module{index}.dll' for index in range(300)] + [
        r'C:\Lumen\PySide6\Qt6Core.dll', r'C:\Lumen\PySide6\Qt6Gui.dll',
        r'C:\Lumen\lumen\bin\libmpv-2.dll']
    api = windows_api(monkeypatch, names)
    result = acceptance.windows_process_memory(1234)
    assert api.enum_calls == 2 and result['module_count'] == 303
    assert result['gui_modules'] == ['Qt6Core.dll', 'Qt6Gui.dll', 'libmpv-2.dll']
    assert api.closed == [5678]


@pytest.mark.parametrize('failure', ['open', 'memory', 'empty-memory', 'modules', 'empty-modules', 'filename', 'limit'])
def test_psapi_cannot_silently_pass_incomplete_or_failed_reads(monkeypatch, failure):
    api = windows_api(monkeypatch, fail=failure)
    with pytest.raises(OSError):
        acceptance.windows_process_memory(1234)
    assert api.closed == ([] if failure == 'open' else [5678])


class TcpTableAPI:
    def __init__(self, rows=(), *, failure=None, data=None, initial_size=4):
        self.data = data if data is not None else struct.pack('<I', len(rows)) + b''.join(
            struct.pack('<6I', 2, 0, socket.htons(port) | 0xabcd0000, 0, 0, pid) for port, pid in rows)
        self.failure, self.initial_size, self.calls = failure, initial_size, 0
        self.GetExtendedTcpTable = Function(self.read)

    def read(self, buffer, pointer, ordered, family, table_class, reserved):
        self.calls += 1
        assert ordered is False and family == 2 and table_class == 3 and reserved == 0
        size = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents
        if buffer is None:
            size.value = self.initial_size
            return 5 if self.failure == 'size-api' else 122
        capacity = size.value
        if self.failure == 'read-api':
            return 5
        if self.failure == 'bad-growth':
            return 122
        if self.failure == 'keeps-growing':
            size.value = capacity + 24
            return 122
        if capacity < len(self.data):
            size.value = len(self.data)
            return 122
        ctypes.memmove(buffer, self.data, len(self.data))
        size.value = 0 if self.failure == 'empty-count' else capacity + 1 if self.failure == 'oversized-count' else len(self.data)
        return 0


def tcp_api(monkeypatch, rows=(), **options):
    api = TcpTableAPI(rows, **options)
    monkeypatch.setattr(acceptance, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(acceptance, '_windows_tcp_library', lambda: api)
    return api


def test_windows_empty_listener_snapshot_is_affirmative_shutdown_evidence_without_connect(monkeypatch):
    api = tcp_api(monkeypatch)
    monkeypatch.setattr(socket, 'create_connection', lambda *args, **kwargs: pytest.fail('Windows must read its listener table'))
    assert acceptance.windows_tcp_listeners() == []
    acceptance.assert_ports_released((43210, 43211))
    assert api.calls == 4
    assert api.GetExtendedTcpTable.restype is ctypes.c_uint32


def test_windows_listener_snapshot_resizes_and_decodes_network_order_low_16_bits(monkeypatch):
    api = tcp_api(monkeypatch, [(43210, 1234), (8097, 5678)])
    assert acceptance.windows_tcp_listeners() == [{'port': 43210, 'pid': 1234}, {'port': 8097, 'pid': 5678}]
    assert api.calls == 3  # size query, growing table, complete retry


@pytest.mark.parametrize('remaining_port', [43210, 43211])
def test_windows_either_service_port_still_listening_under_any_pid_is_a_hard_failure(monkeypatch, remaining_port):
    tcp_api(monkeypatch, [(remaining_port, 9876)])
    with pytest.raises(RuntimeError, match=f"'port': {remaining_port}, 'pid': 9876"):
        acceptance.assert_ports_released((43210, 43211))


def test_windows_other_listener_ports_do_not_imply_this_owner_failed_to_stop(monkeypatch):
    tcp_api(monkeypatch, [(8097, 9876)])
    acceptance.assert_ports_released((43210, 43211))


@pytest.mark.parametrize('failure', ['size-api', 'read-api', 'bad-growth', 'keeps-growing', 'empty-count', 'oversized-count'])
def test_windows_tcp_api_failure_or_incomplete_snapshot_cannot_pass_shutdown(monkeypatch, failure):
    api = tcp_api(monkeypatch, failure=failure)
    with pytest.raises(OSError):
        acceptance.assert_ports_released((43210, 43211))
    assert api.calls <= 5  # allocation retries and OS table size are bounded


@pytest.mark.parametrize('size', [0, 3, acceptance.MAX_TCP_TABLE_BYTES + 1])
def test_windows_tcp_invalid_initial_size_is_rejected_before_allocation(monkeypatch, size):
    api = tcp_api(monkeypatch, initial_size=size)
    with pytest.raises(OSError, match='size'):
        acceptance.windows_tcp_listeners()
    assert api.calls == 1


@pytest.mark.parametrize('data', [
    struct.pack('<I', 1),  # header claims a missing row
    struct.pack('<I', 0xffffffff),  # impossible row count, no iteration/allocation
    struct.pack('<I6I', 1, 5, 0, 1234, 0, 0, 999),  # ESTABLISHED is not a listener row
])
def test_windows_tcp_truncated_or_wrong_state_rows_cannot_pass_shutdown(monkeypatch, data):
    tcp_api(monkeypatch, data=data)
    with pytest.raises(OSError):
        acceptance.assert_ports_released((43210, 43211))


def test_posix_connect_timeout_is_still_a_failure_instead_of_closed_port_evidence(monkeypatch):
    monkeypatch.setattr(acceptance, 'sys', SimpleNamespace(platform='linux'))
    def timeout(*args, **kwargs):
        raise TimeoutError('no RST received')
    monkeypatch.setattr(socket, 'create_connection', timeout)
    with pytest.raises(TimeoutError, match='no RST received'):
        acceptance.assert_ports_released((43210, 43211))


@pytest.mark.parametrize('name,expected', [
    ('Qt6Core.dll', True), ('QT6GUI.DLL', True), ('Qt6Network.dll', True),
    ('QtGui.pyd', True), ('QtCore.abi3.pyd', True), ('libmpv-2.dll', True),
    ('mpv.dll', True), ('mpv-2.dll', True), ('not-Qt6Core.dll', False),
    ('kernel32.dll', False), ('qt.conf', False),
])
def test_module_matching_uses_basename_and_rejects_only_gui_playback_binaries(name, expected):
    assert acceptance._gui_module('C:\\Installed app\\' + name) is expected


def source_entry(monkeypatch, *, runtime=sys):
    # Windows venv python.exe is a redirector: Popen.pid is its wrapper PID,
    # while IPC reports the real interpreter child. Run the base interpreter
    # directly, with this environment's packages explicitly available, so the
    # unchanged production verifier can still require an exact owner PID.
    executable = str(Path(runtime._base_executable).resolve(strict=True)) if runtime.platform == 'win32' else runtime.executable
    monkeypatch.setattr(acceptance, '_command', lambda ignored, arguments: [executable, '-m', 'lumen', *arguments])
    source = str(Path(__file__).resolve().parents[1] / 'src')
    paths = [source, *site.getsitepackages(), *os.environ.get('PYTHONPATH', '').split(os.pathsep)]
    monkeypatch.setenv('PYTHONPATH', os.pathsep.join(dict.fromkeys(path for path in paths if path)))
    return executable


def test_source_fixture_bypasses_windows_venv_redirector_and_preserves_its_packages(monkeypatch, tmp_path):
    redirector = tmp_path / 'venv' / 'Scripts' / 'python.exe'
    base = tmp_path / 'base python' / 'python.exe'
    packages = tmp_path / 'venv' / 'Lib' / 'site-packages'
    inherited = tmp_path / 'inherited modules'
    for executable in (redirector, base):
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'fixture')
    packages.mkdir(parents=True)
    monkeypatch.setattr(site, 'getsitepackages', lambda: [str(packages)])
    monkeypatch.setenv('PYTHONPATH', str(inherited))
    runtime = SimpleNamespace(platform='win32', executable=str(redirector), _base_executable=str(base))
    assert source_entry(monkeypatch, runtime=runtime) == str(base.resolve())
    command = acceptance._command(redirector, ['--background-no-tray', '--data-dir', 'data'])
    assert command == [str(base.resolve()), '-m', 'lumen', '--background-no-tray', '--data-dir', 'data']
    assert str(redirector) not in command
    assert os.environ['PYTHONPATH'].split(os.pathsep) == [
        str(Path(__file__).resolve().parents[1] / 'src'), str(packages), str(inherited)]


def test_source_interpreter_pid_matches_popen_and_can_import_venv_qt(monkeypatch):
    executable = source_entry(monkeypatch)
    process = subprocess.Popen([executable, '-c',
        "import json,os; from PySide6 import QtCore; import lumen; print(json.dumps({'pid':os.getpid(),'qt':QtCore.qVersion()}))"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output, error = process.communicate(timeout=15)
    assert process.returncode == 0, error
    state = json.loads(output)
    assert state['pid'] == process.pid and state['qt'].startswith('6.')


def test_actual_no_tray_entry_http_workers_duplicate_and_exit_and_durable_proof(monkeypatch, tmp_path):
    source_entry(monkeypatch)
    measured = []

    def memory(pid):
        measured.append(pid)
        # Deliberately above the decimal 50 MB target. Functionality still
        # passes and exact numbers survive; the verifier must never trim/lie.
        return {'working_set_bytes': 50_000_001, 'private_usage_bytes': 40_123_456,
                'module_count': 2, 'gui_modules': []}

    monkeypatch.setattr(acceptance, 'windows_process_memory', memory)
    proof = acceptance.verify_standby(sys.executable)
    assert proof['status'] == 'passed' and proof['tray'] is False
    assert proof['native_tray_manual_acceptance'] == 'unverified'
    assert proof['target_bytes'] == 50_000_000
    assert not proof['working_set_target_met'] and not proof['cold_working_set_target_met']
    assert proof['max_working_set_bytes'] == 50_000_001 and proof['max_private_usage_bytes'] == 40_123_456
    assert len(set(measured)) == 1 and len(measured) == 7
    assert set(proof['checks']) == {'ipc_owner_identity', 'lan_authentication', 'lan_catalog', 'lan_range',
                                   'isolated_cover', 'image_worker_entry', 'background_worker_entry',
                                   'single_instance', 'lan_configuration_preserved', 'clean_exit'}
    assert all(proof['checks'].values())
    report = tmp_path / 'durable' / 'standby.json'
    acceptance.write_report(report, proof)
    saved = json.loads(report.read_text(encoding='utf-8'))
    assert saved == proof
    assert 'Bearer ' not in report.read_text(encoding='utf-8')
    assert 'lumen-standby-' not in report.read_text(encoding='utf-8')


def test_gui_module_is_a_hard_gate_and_failed_verification_exits_its_process(monkeypatch):
    source_entry(monkeypatch)
    children = []
    real_popen = acceptance.subprocess.Popen

    def launch(*arguments, **options):
        child = real_popen(*arguments, **options)
        children.append(child)
        return child

    monkeypatch.setattr(acceptance.subprocess, 'Popen', launch)
    monkeypatch.setattr(acceptance, 'windows_process_memory', lambda pid: {
        'working_set_bytes': 20_000_000, 'private_usage_bytes': 18_000_000,
        'module_count': 1, 'gui_modules': ['Qt6Core.dll']})
    with pytest.raises(RuntimeError, match='Qt6Core.dll'):
        acceptance.verify_standby(sys.executable)
    assert len(children) == 1 and children[0].poll() == 0


def test_acceptance_module_import_does_not_preload_qt_or_playback():
    result = subprocess.run([sys.executable, '-c',
        "import sys; import lumen.standby_acceptance; assert not any(name.startswith(('PySide6', 'shiboken6')) or name == 'mpv' for name in sys.modules)"],
        check=True, capture_output=True, timeout=10)
    assert result.returncode == 0


def test_existing_packaged_checks_remain_and_installer_embeds_standby_proof():
    root = Path(__file__).resolve().parents[1]
    verifier = (root / 'scripts/verify-package.py').read_text(encoding='utf-8')
    installer = (root / 'scripts/verify-installer-windows.ps1').read_text(encoding='utf-8')
    assert all(argument in verifier for argument in ('--smoke', '--verify-mpv', '--plugin-worker', '--browser-http-worker'))
    assert "parser.add_argument('--standby-report'" in verifier
    assert '--standby-report' in installer and 'standby = $StandbyProof' in installer
    assert '$VerificationProof | ConvertTo-Json -Depth 12' in installer
    assert '$StandbyProof.executable_sha256 -ne $InstalledExecutableHash' in installer
    assert '$StandbyProof.started_epoch -lt $VerificationStarted' in installer
