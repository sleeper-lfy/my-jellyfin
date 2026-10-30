import time
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog,QListWidget,QDialogButtonBox,QMessageBox
from lumen.core import Library
from lumen.ui import MainWindow
from lumen.merge_history import preview_merge,apply_merge,records
from lumen.merge_ui import MergePreview,show_merge_history,refresh_after_merge
from test_core import add_work


def wait(predicate):
    deadline=time.monotonic()+6
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate()


def test_preview_shows_kept_and_inherited_fields_and_cancel_is_read_only(qapp,library):
    target=add_work(library,'Kept title');source=add_work(library,'Source title')
    library.update_personal(source,rating=8)
    dialog=MergePreview(preview_merge(library,[source],target));dialog.show();qapp.processEvents()
    assert dialog.table.item(0,1).text()=='Kept title' and dialog.table.item(0,3).text()=='Kept title'
    assert dialog.table.item(2,1).text()=='无' and dialog.table.item(2,3).text()=='8'
    assert dialog.table.item(4,3).text()=='2'
    dialog.reject();assert len(library.query())==2 and not records(library,target)
    dialog.deleteLater()


def test_history_entry_undo_restores_records_and_current_player_owner(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'undo-ui');target=add_work(window.library,'Target');source=add_work(window.library,'Source')
    window.player.file=dict(window.library.work(source)['files'][0])
    apply_merge(window.library,preview_merge(window.library,[source],target))
    window.open_details(target,fetch=False);window.show();refresh_after_merge(window,target)
    assert window.player.file['work_id']==target
    assert '合并记录 / 撤销…' in [action.text() for action in window.detail_page.management_menu.actions()]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    show_merge_history(window.detail_page)
    wait(lambda:not window._auxiliary_jobs)
    dialog=next(dialog for dialog in window.findChildren(QDialog) if dialog.windowTitle()=='合并记录 / 撤销')
    choices=dialog.findChild(QListWidget);assert choices.count()==1
    choices.setCurrentRow(0);dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    wait(lambda:not window.jobs)
    assert len(window.library.query())==2 and window.player.file['work_id']==source
    assert records(window.library,target)[0]['status']=='undone'
    window.player.file=None;window.close()
