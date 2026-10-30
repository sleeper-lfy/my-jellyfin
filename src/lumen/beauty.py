"""Bounded, local-only shader configuration shared by playback preferences."""
import hashlib
import math
from pathlib import Path

DEFAULTS={'enabled':False,'smoothing':35,'brighten':15}


def validate(value):
    if not isinstance(value,dict) or not value.keys() <= DEFAULTS.keys():
        raise ValueError('无效美颜设置')
    for key,number in value.items():
        if key=='enabled':
            if type(number) is not bool:raise ValueError('美颜开关须为布尔值')
        elif type(number) not in (int,float) or not math.isfinite(number) or not 0<=number<=100:
            raise ValueError('美颜强度须在 0–100 之间')
    return {**DEFAULTS,**value}


def shader_source(value):
    value=validate(value)
    core=Path(__file__).with_name('shaders').joinpath('beauty-core.glsl').read_text(encoding='utf-8')
    return ('//!HOOK MAIN\n//!BIND HOOKED\n//!DESC Lumen skin-weighted beauty\n'
            'vec4 samplePixel(vec2 p) { return HOOKED_tex(clamp(p, HOOKED_pt * 0.5, vec2(1.0) - HOOKED_pt * 0.5)); }\n'
            '#define pixelStep HOOKED_pt\n'+core+
            '\nvec4 hook() { vec4 original = HOOKED_tex(HOOKED_pos); return vec4(beauty(HOOKED_pos, '
            +format(value['smoothing']/100,'.4f')+', '+format(value['brighten']/100,'.4f')+'), original.a); }\n')


def shader_file(directory,value):
    source=shader_source(value)
    path=Path(directory)/('beauty-'+hashlib.sha256(source.encode()).hexdigest()+'.glsl')
    if not path.is_file():
        from PySide6.QtCore import QSaveFile,QIODevice
        path.parent.mkdir(parents=True,exist_ok=True)
        output=QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly) or output.write(source.encode())<0 or not output.commit():
            raise ValueError('美颜着色器保存失败')
    return str(path)
