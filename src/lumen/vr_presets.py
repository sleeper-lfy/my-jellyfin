"""Directory defaults remain separate from explicit per-file VR preferences."""
import math
from pathlib import Path

SETTING = 'vr_directory_presets'
VR_RANGES = {'fov': (50, 110), 'yaw': (-180, 180), 'pitch': (-85, 85),
             'tracking_sensitivity': (.25, 1.5), 'tracking_smoothing': (0, 150)}
VR_SWITCHES = {'fish', 'headset', 'swap', 'tracking', 'swipe_seek', 'tracking_invert_pitch'}
VR_DEFAULTS = {'fish': False, 'headset': False, 'swap': False, 'tracking': True,
               'swipe_seek': True, 'fov': 90, 'yaw': 0, 'pitch': 0,
               'tracking_sensitivity': 1, 'tracking_smoothing': 40,
               'tracking_invert_pitch': False}


def validate_vr(value):
    if not isinstance(value, dict) or not value.keys() <= VR_RANGES.keys() | VR_SWITCHES:
        raise ValueError('无效 VR 参数')
    for key, number in value.items():
        if key in VR_RANGES:
            low, high = VR_RANGES[key]
            if type(number) not in (int, float) or not math.isfinite(number) or not low <= number <= high:
                raise ValueError('VR 参数超出范围：' + key)
        elif type(number) is not bool:
            raise ValueError('VR 开关须为布尔值')
    return dict(value)


def directory_path(path):
    if not isinstance(path, (str, Path)) or not str(path).strip() or '\0' in str(path):
        raise ValueError('请选择有效的目录路径')
    target = Path(path)
    if not target.is_absolute() or '..' in target.parts:
        raise ValueError('VR 预设必须使用完整目录路径，不允许上级路径引用')
    try:
        resolved = target.resolve()
        if resolved.is_file(): raise ValueError('请选择目录，不能使用视频文件路径')
        return resolved
    except (OSError, RuntimeError) as error:
        raise ValueError('无法解析目录路径') from error


def presets(library):
    return library.setting(SETTING, [])


def set_preset(library, path, values):
    """None removes this directory's rule; per-file overrides are never changed."""
    target = directory_path(path)
    checked = validate_vr(values) if values is not None else None
    entries = [entry for entry in presets(library) if directory_path(entry['path']) != target]
    if checked is not None:
        entries.append({'path': str(target), 'vr': checked})
    library.set_setting(SETTING, entries)


def inherited_vr(library, file_path):
    try: path = Path(file_path).resolve()
    except (OSError, RuntimeError): return {}
    matches = []
    for entry in presets(library):
        try:
            root = directory_path(entry['path'])
            if path.is_relative_to(root):
                matches.append((len(root.parts), validate_vr(entry['vr'])))
        except (KeyError, TypeError, ValueError, OSError):
            # A corrupt or obsolete setting cannot prevent playback.
            continue
    return max(matches, key=lambda entry: entry[0])[1] if matches else {}
