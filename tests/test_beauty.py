import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from lumen.beauty import validate,shader_source
from lumen.media_tools import preferences
from lumen.mpv_backend import MpvMedia
from lumen.player import Player
from test_core import add_work


@pytest.mark.parametrize('value',[{'enabled':1},{'smoothing':True},{'brighten':float('nan')},{'smoothing':-1},{'brighten':101},{'path':'file'},[]])
def test_bad_beauty_values_rejected(value):
    with pytest.raises(ValueError):validate(value)


def test_preferences_merge_and_validation_keep_other_controls(library):
    identifier=add_work(library,'Beauty');file=library.work(identifier)['files'][0]
    preferences(library,file['id'],{'subtitle_delay':.5,'beauty':{'enabled':True,'smoothing':60}})
    saved=preferences(library,file['id'],{'beauty':{'brighten':25}})
    assert saved['subtitle_delay']==.5 and saved['beauty']=={'enabled':True,'smoothing':60,'brighten':25}
    with pytest.raises(ValueError):preferences(library,file['id'],{'beauty':{'enabled':'yes'}})
    assert preferences(library,file['id'])==saved


def test_gpu_shader_stack_keeps_beauty_and_sharpen_independent(qapp,tmp_path):
    # Exercise the real adapter without needing a GPU for property composition.
    from PySide6.QtCore import QObject
    media=MpvMedia.__new__(MpvMedia);QObject.__init__(media)
    media.engine=SimpleNamespace();media.enhanced=False;media.beauty_shader=None
    media.set_beauty({'enabled':True,'smoothing':45,'brighten':20},tmp_path)
    beauty=media.engine.glsl_shaders[0]
    assert Path(beauty).is_file() and '0.4500' in Path(beauty).read_text()
    media.set_enhancement(True);assert len(media.engine.glsl_shaders)==2 and media.engine.glsl_shaders[0]==beauty
    media.set_beauty({'enabled':False},tmp_path);assert len(media.engine.glsl_shaders)==1 and 'sharpen' in media.engine.glsl_shaders[0]
    media.set_enhancement(False);assert media.engine.glsl_shaders==[]


def test_pc_switching_files_resets_and_restores_beauty(qapp,library,video_factory):
    from PySide6.QtTest import QTest
    source=video_factory('Beauty setting.mp4','blue',4);library.import_folder(source.parent,'movie')
    file=library.query()[0]['files'][0]
    player=Player(library)
    try:
        # GUI control persistence uses a fake adapter; shader compilation has its own native check.
        player.open_file(file)
        player.mpv_backend=True
        player.media.set_beauty=lambda *args:None
        player.media.set_subtitle_style=lambda *args:None
        player.beauty_smoothing.setValue(65);player.beauty_brighten.setValue(30);player.beauty_enabled.setChecked(True)
        assert preferences(library,file['id'])['beauty']['smoothing']==65
        player.subtitle_preferences={};player.load_beauty()
        assert not player.beauty_enabled.isChecked() and player.beauty_smoothing.value()==35
        player.subtitle_preferences=preferences(library,file['id']);player.load_beauty()
        assert player.beauty_enabled.isChecked() and player.beauty_brighten.value()==30
        player.beauty_smoothing.setValue(70);player.finish()
        assert preferences(library,file['id'])['beauty']['smoothing']==70
    finally:
        player.mpv_backend=False;player.close()


def test_android_and_pc_use_identical_filter_core():
    root=Path(__file__).parents[1]
    assert (root/'src/lumen/shaders/beauty-core.glsl').read_bytes()==(root/'android/app/src/main/assets/shaders/beauty-core.glsl').read_bytes()
    assert '0.0000' in shader_source({'smoothing':0,'brighten':0})
