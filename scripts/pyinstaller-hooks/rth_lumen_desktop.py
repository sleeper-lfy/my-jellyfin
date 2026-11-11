"""Keep the frozen Windows tray owner Qt-free before the launcher runs.

PyInstaller 6.16's standard PySide6 runtime hook imports QtCore while creating
an embedded qt.conf, even when the application never imports a Qt module.
Custom hooks run first. Skip only that operation for the lightweight owner;
the standard hook still configures plugin/QML/DLL paths and checks bindings.
Each GUI or worker is a fresh process and retains the unmodified Qt hook.
"""


def _lumen_supervisor_arguments(arguments):
    # Match only complete, ordinary owner invocations. Unknown/abbreviated
    # flags conservatively retain standard Qt initialization. In particular,
    # never skip it for --desktop-child, --foreground, verification or workers.
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == '--background':
            index += 1
        elif argument in ('--data-dir', '--host', '--port'):
            index += 1
            if index >= len(arguments) or not arguments[index] or arguments[index].startswith('-'):
                return False
            index += 1
        elif any(argument.startswith(option + '=') and len(argument) > len(option) + 1
                 for option in ('--data-dir', '--host', '--port')):
            index += 1
        else:
            return False
    return True


def _lumen_runtime_hook():
    import sys

    if (sys.platform != 'win32' or not getattr(sys, 'frozen', False)
            or not hasattr(sys, '_MEIPASS') or not _lumen_supervisor_arguments(sys.argv[1:])):
        return

    # This helper imports only stdlib modules. Do not import lumen or PySide6.
    from _pyi_rth_utils import qt
    original_create_embedded_qt_conf = qt.create_embedded_qt_conf

    def create_embedded_qt_conf(qt_bindings, prefix_path):
        if qt_bindings == 'PySide6':
            return None
        return original_create_embedded_qt_conf(qt_bindings, prefix_path)

    qt.create_embedded_qt_conf = create_embedded_qt_conf


_lumen_runtime_hook()
del _lumen_runtime_hook
