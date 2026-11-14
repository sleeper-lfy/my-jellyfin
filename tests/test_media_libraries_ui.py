from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from lumen.ui import MainWindow
from lumen.media_libraries_ui import MediaLibraryDialog,MediaLibrariesPanel
from lumen import media_libraries as ml


def test_native_picker_pasted_multiple_roots_and_cancel_are_not_implicitly_saved(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        dialog=MediaLibraryDialog(window);dialog.name.setText('私人电影');dialog.scan_after.setChecked(False)
        dialog.path.setText(str(tmp_path/'first'));dialog.add_root()
        monkeypatch.setattr('lumen.dialogs.existing_directory',lambda *args:str(tmp_path/'second'))
        dialog.choose_root();assert dialog.roots.count()==2
        dialog.save();assert dialog.saved['name']=='私人电影'
        assert len(ml.get(window.library,dialog.saved['id'])['config']['roots'])==2
        edit=MediaLibraryDialog(window,dialog.saved);assert not edit.kind.isEnabled();edit.name.setText('未保存');edit.reject()
        assert ml.get(window.library,dialog.saved['id'])['name']=='私人电影'
    finally:window.close()


def test_library_selector_scopes_catalog_and_playback_then_removal_preserves_global(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        for name,content in [('A',b'a'),('B',b'b')]:
            root=tmp_path/name;root.mkdir();(root/'Shared.2024.mp4').write_bytes(content)
            item=ml.save(window.library,name,'movie',{'roots':[{'path':str(root)}]});window.library.import_folder(root,'movie',fast=True)
        a,b=ml.list_libraries(window.library);window.refresh_media_libraries();window.open_media_library(a['id']);qapp.processEvents()
        assert window.effective_filters()['media_library_id']==a['id'] and window.heading.text()=='A'
        assert len(window.current_items)==1 and len(window.current_items[0]['files'])==1
        opened=[];monkeypatch.setattr(window.player,'open_file',lambda f:opened.append(f))
        work_id=window.current_items[0]['id'];window.play_work(work_id)
        assert opened[0]['path'].startswith(str(tmp_path/'A')) and opened[0]['_media_library_id']==a['id']
        window.shuffle();window.navigate('home');window.queue_play(0)
        assert opened[-1]['_media_library_id']==a['id']
        panel=MediaLibrariesPanel(window);panel.reload(a['id']);monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes);panel.remove()
        assert len(window.library.query()[0]['files'])==2 and ml.get(window.library,b['id'])
    finally:window.close()


def test_library_rule_editor_does_not_change_global_or_other_library(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        window.library.set_setting('partition:movie',{'plugin':'global'})
        a=ml.save(window.library,'A','movie',{'roots':[],'plugin':'first','naming':{'filename':'A-{title}'}})
        b=ml.save(window.library,'B','movie',{'roots':[],'plugin':'second','naming':{'filename':'B-{title}'}})
        editor=MediaLibraryDialog(window,a);editor.naming.filename.setText('Changed-{title}');editor.scan_after.setChecked(False);editor.save()
        assert editor.saved['config']['naming']['filename']=='Changed-{title}'
        assert ml.get(window.library,b['id'])['config']['naming']['filename']=='B-{title}'
        assert window.library.setting('partition:movie')['plugin']=='global'
    finally:window.close()


def test_home_uses_named_library_cards_and_long_names_do_not_expand_window(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        a=ml.save(window.library,'家庭电影','movie',{'roots':[]});b=ml.save(window.library,'私人收藏'*15,'vr',{'roots':[]})
        window.refresh_media_libraries();window.resize(1024,700);window.show();window.navigate('home')
        for _ in range(6):qapp.processEvents()
        assert {tile.title for tile in window.home_page.tiles.values()}=={'家庭电影','私人收藏'*15}
        window.home_page.tiles['library:'+str(b['id'])].click()
        for _ in range(4):qapp.processEvents()
        assert window.media_library_id==b['id'] and window.heading.text()=='私人收藏'*15
        assert window.width()==1024 and window.heading.width()<window.browse_page.width()
        assert window.heading.toolTip()=='私人收藏'*15
    finally:window.close()


def test_scoped_actions_never_choose_or_delete_another_library_copy(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        for name in ['A','B']:
            root=tmp_path/name;root.mkdir();(root/'Shared.2024.mp4').write_bytes(name.encode())
            ml.save(window.library,name,'movie',{'roots':[{'path':str(root)}]});window.library.import_folder(root,'movie',fast=True)
        a,b=ml.list_libraries(window.library);window.refresh_media_libraries();window.open_media_library(a['id'])
        work_id=window.current_items[0]['id'];other=window.library.work(work_id,b['id'])['files'][0]
        window.library.set_watched(work_id,'completed',other['id'])
        opened=[];revealed=[];monkeypatch.setattr(window,'play_file',lambda f:opened.append(f));monkeypatch.setattr(window,'reveal_file_path',lambda p:revealed.append(p))
        window.catalog_restart(work_id);window.reveal_work_file(work_id)
        assert opened[0]['_media_library_id']==a['id'] and revealed[0].startswith(str(tmp_path/'A'))
        assert window.library.work(work_id,b['id'])['files'][0]['completed']==1
        planned=[]
        def cancel(dialog):
            planned.append(dialog.detailedText());return QMessageBox.StandardButton.Cancel
        monkeypatch.setattr(QMessageBox,'exec',cancel)
        window.delete_work_files(work_id)
        assert len(planned)==1 and str(tmp_path/'A'/'Shared.2024.mp4')==planned[0]
        errors=[];monkeypatch.setattr(QMessageBox,'warning',lambda *args:errors.append(args[-1]))
        window.delete_work_files(work_id,[other['id']]);assert errors and len(planned)==1
        monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
        window.remove_catalog_work(work_id)
        assert not window.library.query({'media_library_id':a['id']})
        assert window.library.work(work_id,b['id'])['files'][0]['completed']==1
        assert len(window.library.work(work_id)['files'])==2
    finally:window.close()
