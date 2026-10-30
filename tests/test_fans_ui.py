import time
from PySide6.QtCore import Qt,QEventLoop,QTimer
from PySide6.QtWidgets import QDialog,QListWidget,QDialogButtonBox,QLineEdit
from lumen.ui import MainWindow
from lumen.import_ui import ImportDialog
from lumen.library_tools_ui import LibraryTools
from test_core import add_work


def settle(app,window):
    deadline=time.monotonic()+8
    while (window.jobs or window._auxiliary_jobs or window._browse_job is not None or window._browse_pending is not None) and time.monotonic()<deadline:
        loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
    app.processEvents()
    assert not window.jobs and not window._auxiliary_jobs


def test_fans_navigation_import_monitor_and_detail_never_offer_film_scraping(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'fans-ui')
    work_id=add_work(window.library,'Sample author',kind='fans',metadata={'creator':'Sample author','fans_roots':['/media/author']})
    try:
        window.show();window.navigate('home')
        assert window.home_page.tiles['fans'].subtitle=='1 位作者'
        window.home_page.tiles['fans'].click()
        assert window.section=='fans' and len(window.current_items)==1 and window.heading.text()=='Fans'
        form=ImportDialog(window);assert form.kind.findData('fans')>=0
        form.kind.setCurrentIndex(form.kind.findData('fans'));assert '第一层作者' in form.message.text();form.close()
        window.library.set_setting('watched_folders',[{'path':'/media/fans','kind':'fans','enabled':True}])
        tools=LibraryTools(window);assert 'Fans' in tools.list.item(0).text();tools.close()
        window.open_details(work_id,fetch=False);detail=window.detail_page
        actions=[action.text() for action in detail.management_menu.actions()]
        assert '合并同作者文件夹…' in actions
        assert '刮削匹配…' not in actions and '从 NFO 补充图片…' not in actions
        assert detail.refresh_resources.isHidden() and detail.resources_heading.isHidden()
        window.library.set_setting('partition:fans',{'plugin':'must-not-run'})
        window.auto_scrape_import('/media/fans','fans');assert not window.jobs
    finally:window.close();settle(qapp,window)


def test_fans_merge_dialog_merges_logical_author_and_preserves_file_ids(qapp,tmp_path,monkeypatch):
    monkeypatch.setattr('lumen.merge_ui.MergePreview.exec',lambda self:1)
    window=MainWindow(tmp_path/'fans-merge-ui')
    target=add_work(window.library,'Author one',kind='fans',metadata={'creator':'Author one','fans_roots':['/media/one']})
    source=add_work(window.library,'Author one alternative',kind='fans',metadata={'creator':'Author one alternative','fans_roots':['/media/two']})
    original_ids={file['id'] for work in window.library.query({'kinds':['fans']}) for file in work['files']}
    try:
        window.show();window.navigate('fans');window.open_details(target,fetch=False)
        window.detail_page.merge_fans_folders();settle(qapp,window)
        dialog=next(dialog for dialog in window.findChildren(QDialog) if dialog.windowTitle()=='合并同作者文件夹')
        choices=dialog.findChild(QListWidget,'fansMergeChoices');assert choices.count()==1
        assert choices.item(0).data(Qt.ItemDataRole.UserRole)==source
        choices.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.findChild(QLineEdit,'fansMergeCreator').setText('Unified author')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click();settle(qapp,window)
        works=window.library.query({'kinds':['fans']});assert len(works)==1 and works[0]['id']==target
        assert works[0]['metadata']['creator']=='Unified author'
        assert {file['id'] for file in works[0]['files']}==original_ids
        assert window.detail_page.work_id==target
    finally:window.close();settle(qapp,window)
