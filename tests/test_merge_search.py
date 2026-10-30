from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox,QMessageBox
from lumen.merge_ui import MergePicker
from lumen.ui import MainWindow
from test_core import add_work


def test_merge_search_title_id_alias_path_and_hidden_selection(qapp,library):
    first=add_work(library,'First',metadata={'aliases':['Other name']})
    second=add_work(library,'Second')
    picker=MergePicker(library.query({'local':False}));picker.show();qapp.processEvents()
    ok=picker.buttons.button(QDialogButtonBox.StandardButton.Ok);assert not ok.isEnabled()
    picker.search.setText('other name');assert sum(not picker.items.item(i).isHidden() for i in range(2))==1
    row=next(i for i in range(2) if not picker.items.item(i).isHidden());picker.items.setCurrentRow(row)
    assert picker.selected_id()==first and ok.isEnabled()
    picker.search.setText('not found');assert picker.selected_id() is None and not ok.isEnabled()
    picker.search.setText(f'#{second} /media');assert sum(not picker.items.item(i).isHidden() for i in range(2))==1
    picker.search.clear();assert all(not picker.items.item(i).isHidden() for i in range(2))
    picker.close()


def test_merge_search_selected_result_is_the_work_merged(qapp,tmp_path,monkeypatch):
    import time
    from PySide6.QtTest import QTest
    window=MainWindow(tmp_path/'merge-ui');target=add_work(window.library,'Target',kind='vr')
    source=add_work(window.library,'Wanted',kind='vr');other=add_work(window.library,'Other',kind='vr')
    window.open_details(target,fetch=False);window.show()
    def choose(picker):
        picker.search.setText('Wanted')
        picker.items.setCurrentRow(next(i for i in range(picker.items.count()) if not picker.items.item(i).isHidden()))
        return 1
    monkeypatch.setattr(MergePicker,'exec',choose)
    monkeypatch.setattr('lumen.merge_ui.MergePreview.exec',lambda self:1)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    window.detail_page.merge_duplicate();deadline=time.monotonic()+6
    while (window._auxiliary_jobs or window.jobs) and time.monotonic()<deadline:QTest.qWait(10)
    assert not window.jobs and not window._auxiliary_jobs
    assert {work['id'] for work in window.library.query()}=={target,other}
    assert len(window.library.work(target)['files'])==2 and window.detail_page.work_id==target
    window.close()
