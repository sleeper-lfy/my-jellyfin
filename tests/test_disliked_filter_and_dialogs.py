import pytest
from PySide6.QtWidgets import QFileDialog

from lumen import dialogs
from lumen.ui import FilterDialog, filter_tokens
from test_browse_queue_scope import local_work
from test_server import lan


def test_disliked_filter_combines_with_other_conditions_and_resets_as_draft(qapp):
    dialog=FilterDialog({'disliked':True,'tags_all':['Drama'],'kinds':['movie']})
    assert dialog.disliked.isChecked() and dialog.filters()['disliked'] is True
    assert ('disliked',None,'不喜欢') in filter_tokens(dialog.filters())
    dialog.disliked.setChecked(False)
    assert 'disliked' not in dialog.filters() and dialog.filters()['tags_all']==['Drama']
    dialog.favorite.setChecked(True);dialog.disliked.setChecked(True)
    assert not dialog.favorite.isChecked()
    dialog.disliked.setChecked(True);dialog.reset()
    assert not dialog.disliked.isChecked() and 'disliked' not in dialog.filters()
    dialog.reject()


def test_disliked_filter_api_and_saved_list_keep_the_queue_scope(lan,library,tmp_path):
    client,_,source,_=lan
    disliked=local_work(library,source,tmp_path,'Disliked movie',metadata={'tags':['Drama']})
    liked=local_work(library,source,tmp_path,'Liked movie',metadata={'tags':['Drama']})
    vr=local_work(library,source,tmp_path,'Disliked VR',kind='vr')
    library.update_personal(disliked,disliked=True);library.update_personal(vr,disliked=True)
    library.update_personal(liked,favorite=True)
    path='/api/works?kind=movie&disliked=true&tag=Drama'
    result=client.get(path).json()
    assert [item['id'] for item in result['items']]==[disliked]
    shuffled=client.post('/api/queue/from-browse',json={'browse_path':path})
    assert shuffled.status_code==200
    assert shuffled.json()['ids']==[disliked]
    assert client.post('/api/lists',json={'name':'Cleanup','filters':{'disliked':True,'kinds':['movie']}}).status_code==200
    assert [item['id'] for item in client.get('/api/works?list=Cleanup').json()['items']]==[disliked]
    assert client.get('/api/works?list=Cleanup&kind=vr').json()['total']==0
    from pathlib import Path
    assert all(Path(file['path']).is_file() for item in (disliked,liked,vr) for file in library.work(item)['files'])


@pytest.mark.parametrize('platform,native',[('win32',True),('linux',False)])
def test_folder_picker_uses_windows_shell_and_keeps_pasted_initial_path(qapp,tmp_path,monkeypatch,platform,native):
    monkeypatch.setattr(dialogs.sys,'platform',platform)
    folder=tmp_path/'Directory with spaces';folder.mkdir()
    picker=dialogs._picker(None,'Choose directory',str(folder))
    try:
        assert picker.testOption(QFileDialog.Option.DontUseNativeDialog) is not native
        assert picker.directory().absolutePath()==str(folder)
        assert bool(picker.styleSheet()) is not native
    finally:picker.deleteLater()
    monkeypatch.setattr(QFileDialog,'exec',lambda self:0)
    assert dialogs.existing_directory(None,'Choose',str(folder))==''
