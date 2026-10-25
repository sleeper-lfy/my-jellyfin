"""Create the compatibility audio output as a native Qt QML object.

Python-constructed QAudioOutput uses a PySide virtual notify wrapper. FFmpeg
teardown can call that wrapper while holding Qt's connection lock, creating a
lock inversion with a GUI signal connection waiting for that lock with the GIL
held. A QML-created AudioOutput has no Python virtual notify wrapper.
"""
from PySide6.QtMultimedia import QAudioOutput
from PySide6.QtQml import QQmlComponent, QQmlEngine
import shiboken6


def native_audio_output(parent):
    engine=QQmlEngine()
    component=QQmlComponent(engine)
    # loadFromModule is synchronous for this installed Qt type. Unlike setData
    # with an import statement it needs no nested event loop during construction.
    component.loadFromModule('QtMultimedia','AudioOutput',QQmlComponent.CompilationMode.PreferSynchronous)
    if not component.isReady():
        errors='; '.join(error.toString() for error in component.errors())
        raise RuntimeError('无法加载兼容播放器音频组件 QtMultimedia.AudioOutput：'+(errors or str(component.status())))
    audio=component.create()
    if not isinstance(audio,QAudioOutput) or shiboken6.createdByPython(audio):
        raise RuntimeError('兼容播放器音频组件必须由 Qt 原生创建')
    audio.setParent(parent)
    QQmlEngine.setObjectOwnership(audio,QQmlEngine.ObjectOwnership.CppOwnership)
    # Keep both Qt ownership and Python references explicit. The engine remains
    # a child of audio until audio's QObject destructor releases its children.
    engine.setParent(audio)
    component.setParent(engine)
    audio._lumen_qml_engine=engine
    audio._lumen_qml_component=component
    return audio
