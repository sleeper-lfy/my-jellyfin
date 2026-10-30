from PySide6.QtWidgets import QPushButton, QComboBox, QCheckBox
from lumen.actor_batch_ui import show_actor_batch
from lumen.ui import MainWindow
from test_actor_plugins import provider


def test_batch_ui_uses_selected_scope_source_and_fill_only_default(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data');provider(window.library)
    window.current_items=[{'name':'Local actor','aliases':['Alias']}]
    dialog=show_actor_batch(window)
    assert show_actor_batch(window) is dialog
    overwrite=dialog.findChild(QCheckBox,'batchActorOverwrite');assert not overwrite.isChecked()
    scope=dialog.findChild(QComboBox,'batchActorScope');scope.setCurrentIndex(1)
    calls=[];jobs=[]
    result={'updated':1,'skipped':0,'ambiguous':1,'unmatched':0,'failed':0,
            'items':[{'name':'Local actor','reason':'已保存头像'}]}
    def batch(library,plugin_ids,**kwargs):calls.append((plugin_ids,kwargs));return result
    monkeypatch.setattr('lumen.actor_batch_ui.fetch_actor_portraits',batch)
    def run_job(title,function,callback):
        jobs.append(title)
        def progress(*args):pass
        progress.cancelled=lambda:False
        callback(function(window.library,progress))
    monkeypatch.setattr(window,'run_job',run_job)
    try:
        dialog.findChild(QPushButton,'startBatchActorPhotos').click()
        assert jobs==['批量获取演员头像']
        assert calls[0][0]==['tvmaze'] and calls[0][1]['replace'] is False
        assert calls[0][1]['names']==['Local actor','Alias']
        assert '更新 1 位' in window.status.text() and '需确认 1 位' in window.status.text()
        assert window.actor_batch_result_dialog.isVisible()
        window.actor_batch_result_dialog.close()
    finally:dialog.close();qapp.processEvents();window.close()


def test_no_enabled_actor_plugin_disables_batch_start(qapp,tmp_path):
    window=MainWindow(tmp_path/'empty');dialog=show_actor_batch(window)
    try:
        assert not dialog.findChild(QPushButton,'startBatchActorPhotos').isEnabled()
        assert dialog.findChild(QComboBox,'batchActorSources').count()==0
    finally:dialog.close();qapp.processEvents();window.close()
