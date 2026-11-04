import json
from pathlib import Path
import pytest
import httpx
from lumen.core import Library
from lumen.media_tools import preferences
from lumen.server import LanServer
from lumen.vr_presets import set_preset, inherited_vr


def imported(library, root, name='ABC-123.mp4'):
    root.mkdir(parents=True, exist_ok=True); path=root/name; path.write_bytes(name.encode())
    library.import_folder(root,'vr',fast=True)
    return next(file for work in library.query({'kinds':['vr']}) for file in work['files'] if file['path']==str(path))


def test_longest_directory_match_is_dynamic_and_new_files_inherit(library,tmp_path):
    root=tmp_path/'vr'; file=imported(library,root/'fish')
    set_preset(library,root,{'fov':90,'headset':False})
    set_preset(library,root/'fish',{'fov':70,'fish':True,'headset':True})
    assert preferences(library,file['id'])['vr']=={'fov':70,'fish':True,'headset':True}
    assert library.db.execute('SELECT COUNT(*) FROM playback_preferences').fetchone()[0]==0
    set_preset(library,root/'fish',{'fov':75,'fish':True})
    assert preferences(library,file['id'])['vr']['fov']==75
    added=imported(library,root/'fish','ABC-456.mp4')
    assert preferences(library,added['id'])['vr']['fov']==75
    assert inherited_vr(library,tmp_path/'vr-other'/'file.mp4')=={}
    set_preset(library,root/'fish',None)
    assert preferences(library,file['id'])['vr']=={'fov':90,'headset':False}


def test_file_override_wins_and_unrelated_save_does_not_pin_defaults(library,tmp_path):
    root=tmp_path/'vr'; file=imported(library,root)
    set_preset(library,root,{'fov':70,'fish':True})
    preferences(library,file['id'],{'vr':{'fov':80},'subtitle_delay':1.5})
    set_preset(library,root,{'fov':90,'fish':False})
    effective=preferences(library,file['id'],{'subtitle_size':28})
    assert effective['vr']=={'fov':80,'fish':False}
    raw=json.loads(library.db.execute('SELECT value FROM playback_preferences WHERE file_id=?',(file['id'],)).fetchone()[0])
    assert raw['vr']=={'fov':80} and '_vr_inherited' not in raw
    restored=preferences(library,file['id'],{'vr':None})
    assert restored['vr']=={'fov':90,'fish':False} and restored['subtitle_delay']==1.5
    reopened=Library(library.directory)
    try:assert preferences(reopened,file['id'])==restored
    finally:reopened.close()


@pytest.mark.parametrize('value',[{'fov':True},{'fov':49},{'yaw':float('nan')},{'pitch':86},{'tracking_sensitivity':2},{'tracking_smoothing':151},{'fish':1},{'unknown':True},[]])
def test_invalid_values_do_not_change_existing_preset(library,tmp_path,value):
    set_preset(library,tmp_path,{'fov':90})
    with pytest.raises(ValueError):set_preset(library,tmp_path,value)
    assert inherited_vr(library,tmp_path/'file.mp4')=={'fov':90}


@pytest.mark.parametrize('path',['','relative/path','/tmp/../secret','/tmp/\x00invalid'])
def test_invalid_paths_rejected(library,path):
    with pytest.raises(ValueError):set_preset(library,path,{'fov':90})
    assert not library.setting('vr_directory_presets',[])


def test_authenticated_api_exposes_effective_settings_and_clears_only_file_vr(library,tmp_path):
    root=tmp_path/'vr'; file=imported(library,root);set_preset(library,root,{'fov':65,'fish':True})
    server=LanServer(library.directory,host='127.0.0.1',port=0,discovery_port=None);server.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.port}',headers={'Authorization':'Bearer '+server.token},trust_env=False) as client:
            route=f"/api/files/{file['id']}/preferences"
            assert client.get(route,headers={'Authorization':''}).status_code==401
            assert client.get(route).json()['vr']['fov']==65
            assert client.post(route,json={'vr':{'fov':80},'subtitle_size':26}).status_code==200
            reset=client.post(route,json={'vr':None}).json()
            assert reset['vr']['fov']==65 and reset['subtitle_size']==26
    finally:server.stop()


def test_directory_preset_dialog_saves_and_cancels(qapp,tmp_path):
    from lumen.ui import MainWindow
    from lumen.vr_presets_ui import VrPresetDialog
    window=MainWindow(tmp_path/'data'); root=tmp_path/'vr'
    try:
        dialog=VrPresetDialog(window,root);dialog.fields['fov'].setValue(75);dialog.reject()
        assert inherited_vr(window.library,root/'file.mp4')=={}
        dialog=VrPresetDialog(window,root);dialog.fields['fov'].setValue(65);dialog.fields['fish'].setCurrentIndex(1);dialog.save()
        assert inherited_vr(window.library,root/'file.mp4')['fov']==65
        assert inherited_vr(window.library,root/'file.mp4')['fish'] is True
        VrPresetDialog(window,root).remove();assert inherited_vr(window.library,root/'file.mp4')=={}
    finally:window.close()


def test_file_path_cannot_be_used_as_directory_rule(library,tmp_path):
    path=tmp_path/'video.mp4';path.write_bytes(b'video')
    with pytest.raises(ValueError,match='目录'):set_preset(library,path,{'fov':90})


def test_old_client_echo_does_not_pin_inherited_values(library,tmp_path):
    root=tmp_path/'vr';file=imported(library,root)
    set_preset(library,root,{'fov':70,'fish':True})
    echoed=preferences(library,file['id']);echoed['subtitle_size']=28
    preferences(library,file['id'],echoed)
    set_preset(library,root,{'fov':90,'fish':False})
    assert preferences(library,file['id'])['vr']=={'fov':90,'fish':False}
    echoed=preferences(library,file['id']);echoed['vr']['fov']=80
    preferences(library,file['id'],echoed)
    set_preset(library,root,{'fov':100,'fish':True})
    assert preferences(library,file['id'])['vr']=={'fov':80,'fish':True}
