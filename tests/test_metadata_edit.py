import copy
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QLineEdit,QPushButton,QPlainTextEdit,QInputDialog
from lumen.ui import MainWindow
from lumen.metadata_ui import MetadataEditor,MetadataList
from lumen.metadata_edit import snapshot,save_lists
from test_gallery_downloads import manager_for


def add(library,tmp_path,name):
    folder=tmp_path/name;folder.mkdir();(folder/(name+'.mp4')).write_bytes(name.encode())
    library.import_folder(folder,'movie',fast=True)
    work=library.query({'folder':str(folder)})[0]
    library.edit_metadata(work['id'],{'tags':['旧标签'],'actors':[{'name':'原姓名','gender':'unknown','aliases':['旧别名'],'photo_cache':'cached.jpg','photo_source_url':'https://example.org/source','role':'原角色'}],'overview':'保留简介'},['overview'])
    library.update_personal(work['id'],favorite=True,rating=8)
    return work['id']


def test_detail_edits_only_current_work_preserves_actor_assets_and_locks(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        one=add(window.library,tmp_path,'One');two=add(window.library,tmp_path,'Two')
        other=copy.deepcopy(snapshot(window.library,two))
        window.open_details(one,fetch=False)
        assert window.detail_page.findChild(QPushButton,'editWorkTags')
        assert window.detail_page.findChild(QPushButton,'editWorkActors')
        dialog=MetadataEditor(window,one,'actors')
        dialog.editors['tags'].replace(0,'新标签')
        actor=copy.deepcopy(dialog.editors['actors'].values[0]);actor['name']='新姓名'
        dialog.editors['actors'].replace(0,actor);dialog.save()
        assert dialog.result()==QDialog.DialogCode.Accepted
        saved=window.library.work(one)
        assert saved['metadata']['actors'][0]['photo_cache']=='cached.jpg'
        assert saved['metadata']['actors'][0]['photo_source_url']=='https://example.org/source'
        assert snapshot(window.library,one)['actors'][0]['gender']=='unknown'
        assert saved['favorite'] and saved['rating']==8 and saved['metadata']['overview']=='保留简介'
        assert set(saved['locked'])=={'overview','tags','actors'}
        assert snapshot(window.library,two)==other
        assert window.library.query({'tags_all':['新标签']})[0]['id']==one
        assert window.library.query({'actor':'新姓名'})[0]['id']==one
    finally:window.close()


def test_cancel_and_remove_all_are_distinct_and_scraping_cannot_restore_deleted_lists(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        identifier=add(window.library,tmp_path,'Film')
        original=snapshot(window.library,identifier)
        dialog=MetadataEditor(window,identifier)
        for editor in dialog.editors.values():
            editor.items.setCurrentRow(0);editor.findChild(QPushButton,editor.field+'Remove').click()
        dialog.reject();assert snapshot(window.library,identifier)==original
        dialog=MetadataEditor(window,identifier)
        for editor in dialog.editors.values():editor.items.setCurrentRow(0);editor.remove()
        dialog.save()
        provider=manager_for(window.library)
        provider.merge('catalog-json',{'id':'film','title':'Film','url':'http://localhost/film','tags':['返回的标签'],'actors':[{'name':'返回的演员'}]},identifier)
        saved=snapshot(window.library,identifier)
        assert saved['tags']==[] and saved['actors']==[]
    finally:window.close()


def test_stale_save_rejected_without_losing_background_changes(library,tmp_path):
    identifier=add(library,tmp_path,'Film');before=snapshot(library,identifier)
    library.edit_metadata(identifier,{'tags':['后台标签'],'overview':'新的简介'},['overview'])
    with pytest.raises(ValueError,match='编辑期间已更新'):
        save_lists(library,identifier,{'tags':['本地标签']},before)
    assert snapshot(library,identifier)['tags']==['后台标签']
    save_lists(library,identifier,{'actors':[]},before)
    assert snapshot(library,identifier)['overview']=='新的简介'


def test_tag_buttons_add_edit_and_validate_duplicates(qapp,monkeypatch):
    widget=MetadataList('tags',['已有'])
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**kw:('新增标签',True))
    widget.findChild(QPushButton,'tagsAdd').click()
    assert widget.values==['已有','新增标签']
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**kw:('改名',True))
    widget.findChild(QPushButton,'tagsEdit').click()
    assert widget.values==['已有','改名']
    with pytest.raises(ValueError,match='重复'):widget.replace(-1,'已有')
    assert len(widget.values)==2


def test_actor_form_add_and_edit_preserve_unexposed_fields(qapp):
    widget=MetadataList('actors',[])
    def fill(name):
        dialog=next(child for child in widget.findChildren(QDialog) if child.isVisible())
        dialog.findChild(QLineEdit,'actorName').setText(name)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    QTimer.singleShot(0,lambda:fill('新演员'))
    widget.findChild(QPushButton,'actorsAdd').click()
    assert widget.values[0]['name']=='新演员'
    widget.values[0]['photo_cache']='unchanged.jpg'
    QTimer.singleShot(0,lambda:fill('改名演员'))
    widget.findChild(QPushButton,'actorsEdit').click()
    assert widget.values[0]['name']=='改名演员' and widget.values[0]['photo_cache']=='unchanged.jpg'


def test_general_metadata_dialog_uses_same_list_editors(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        identifier=add(window.library,tmp_path,'Film');window.open_details(identifier,fetch=False)
        found=[]
        def inspect():
            dialog=next(d for d in window.detail_page.findChildren(QDialog) if d.isVisible())
            found.extend(dialog.findChildren(MetadataList))
            assert len(dialog.findChildren(QPlainTextEdit))==1
            dialog.reject()
        QTimer.singleShot(0,inspect);window.detail_page.edit()
        assert {editor.field for editor in found}=={'tags','actors'}
    finally:window.close()
