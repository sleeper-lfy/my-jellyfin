from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QMessageBox,QPushButton,QScrollArea
from lumen.ui import MainWindow
from lumen.library_tools_ui import LibraryTools
from lumen.media_management_ui import (CategoryRules,DirectoryRuleDialog,effective_directory_rule,
    show_media_management,write_settings)
from lumen.organize_templates import rule_key


def test_category_saves_source_order_destination_and_unknown_config(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        destination=str(tmp_path/'sorted')
        window.library.set_setting('partition:movie',{'plugin':'primary','destination':destination,'future_setting':23})
        window.library.set_setting('numbered_fallbacks:movie',['backup'])
        editor=CategoryRules(window);editor.kind.setCurrentIndex(editor.kind.findData('movie'))
        editor.naming.filename.setText('{code}')
        editor.save()
        assert window.library.setting('partition:movie')=={'plugin':'primary','destination':destination,'future_setting':23}
        assert window.library.setting('numbered_fallbacks:movie')==['backup']
        assert window.library.setting(rule_key('movie'))['filename']=='{code}'
    finally:window.close()


def test_directory_effective_rules_distinguish_source_target_and_default(library,tmp_path):
    target=str(tmp_path/'target');source=str(tmp_path/'incoming')
    library.set_setting('partition:movie',{'plugin':'primary','destination':target})
    library.set_setting('numbered_fallbacks:movie',['backup'])
    library.set_setting(rule_key('movie'),{'folder':'{title}','filename':'{stem}'})
    library.set_setting(rule_key('movie',target),{'folder':'{code}','filename':'{code}'})
    rule=effective_directory_rule(library,{'kind':'movie','path':source})
    assert rule['destination']==target and rule['path']==source
    assert rule['plugin_inherited'] and not rule['naming_inherited'] and rule['fallbacks']==['backup']
    manual=effective_directory_rule(library,{'kind':'movie','path':source,'plugin':'','destination':''})
    assert manual['destination']=='' and manual['fallbacks']==[] and manual['naming_inherited']
    assert effective_directory_rule(library,{'kind':'movie','path':source},{rule_key('movie',target):None})['naming_inherited']


def test_directory_draft_cancel_is_read_only_and_target_template_is_staged(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        destination=str(tmp_path/'sorted');config={'kind':'movie','path':str(tmp_path/'incoming'),'destination':destination,'enabled':True}
        window.library.set_setting('watched_folders',[config]);dialog=LibraryTools(window);dialog.list.setCurrentRow(0)
        editor=DirectoryRuleDialog(window,config)
        editor.custom_naming.setChecked(True);editor.naming.filename.setText('{code}');editor.reject()
        assert window.library.setting(rule_key('movie',destination),None) is None
        editor=DirectoryRuleDialog(window,config)
        editor.custom_naming.setChecked(True);editor.naming.filename.setText('{code}');editor.save()
        assert editor.result()==QDialog.DialogCode.Accepted
        assert list(editor.naming_update)==[rule_key('movie',destination)]
        assert window.library.setting(rule_key('movie',destination),None) is None
        dialog.folders[0]=editor.entry;dialog.naming_updates.update(editor.naming_update)
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
        dialog.save()
        assert window.library.setting(rule_key('movie',destination))['filename']=='{code}'
        assert window.library.setting(rule_key('movie',config['path']),None) is None
        dialog.close()
    finally:window.close()


def test_context_buttons_disable_without_selection_and_vr_only_for_vr(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        window.library.set_setting('watched_folders',[{'kind':'movie','path':str(tmp_path/'movies')},{'kind':'vr','path':str(tmp_path/'vr')}])
        panel=LibraryTools(window);panel.kind_filter.setCurrentIndex(0)
        assert all(not button.isEnabled() for button in panel.context_controls)
        panel.list.setCurrentRow(0)
        assert all(button.isEnabled() for button in panel.context_controls) and not panel.vr_button.isEnabled()
        panel.list.setCurrentRow(1);assert panel.vr_button.isEnabled()
        panel.close()
    finally:window.close()


def test_management_reuses_modeless_page_and_export_has_explicit_scope(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        dialog=show_media_management(window,'sources');qapp.processEvents()
        assert not dialog.isModal() and dialog.tabs.currentIndex()==1
        assert show_media_management(window,'export') is dialog and dialog.tabs.currentIndex()==4
        assert dialog.export_kind.count()==4
        called=[];monkeypatch.setattr('lumen.nfo_export_ui.export_dialog',lambda w,ids:called.append(ids))
        root=tmp_path/'incoming';root.mkdir();(root/'Film.mp4').write_bytes(b'demo')
        window.library.import_folder(root,'movie',fast=True)
        dialog.export_kind.setCurrentIndex(dialog.export_kind.findData('movie'));dialog.export_nfo()
        assert called==[[window.library.query()[0]['id']]]
        dialog.close()
    finally:window.close()


def test_directory_editor_scrolls_in_short_window(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        editor=DirectoryRuleDialog(window,{'kind':'movie','path':str(tmp_path/'incoming')});editor.resize(640,400);editor.show();qapp.processEvents()
        scroll=editor.findChild(QScrollArea)
        assert editor.height()==400 and scroll.verticalScrollBar().maximum()>0
        editor.close()
    finally:window.close()


def test_changing_source_keeps_unsaved_target_naming(qapp,tmp_path):
    window=MainWindow(tmp_path/'data')
    try:
        editor=DirectoryRuleDialog(window,{'kind':'movie','path':str(tmp_path/'incoming'),'destination':str(tmp_path/'target')})
        editor.custom_naming.setChecked(True);editor.naming.filename.setText('{code} - {version}')
        editor.plugin.setCurrentIndex(editor.plugin.findData(''))
        assert editor.naming.filename.text()=='{code} - {version}' and editor.custom_naming.isChecked()
        editor.target.setText(str(tmp_path/'second'));editor.update_summary()
        editor.target.setText(str(tmp_path/'target'));editor.update_summary()
        assert editor.naming.filename.text()=='{code} - {version}'
        editor.close()
    finally:window.close()


def test_management_short_window_and_unsaved_close_guard(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'data')
    try:
        dialog=show_media_management(window);dialog.resize(850,500);qapp.processEvents()
        assert dialog.height()<=500
        for index in range(dialog.tabs.count()):
            dialog.tabs.setCurrentIndex(index);qapp.processEvents()
            assert dialog.tabs.tabBar().tabRect(index).right()<dialog.tabs.tabBar().width()
        dialog.directories.folders.append({'kind':'movie','path':str(tmp_path/'incoming')})
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Cancel)
        dialog.close();assert dialog.isVisible()
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Discard)
        dialog.close();qapp.processEvents();assert window.media_management_dialog is None
        reopened=show_media_management(window);assert reopened.directories.folders==[];reopened.close()
    finally:window.close()
