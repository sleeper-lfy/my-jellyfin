"""Real Qt geometry regressions for compact management windows."""
from pathlib import Path

from PySide6.QtCore import QPoint,QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QWidget,QLabel,QPushButton,QTableWidget,QDialogButtonBox,QScrollArea,QDialog

from lumen.theme import STYLE
from lumen.versions_ui import show_versions
from lumen.vr_presets_ui import VrPresetDialog
from lumen.organize_ui import Organizer,show_naming_rules
from lumen.metadata_health_ui import show_metadata_health


class ToolWindow(QWidget):
    def __init__(self,library):
        super().__init__();self.library=library;self.section='movie';self.status=QLabel(self);self.detail_page=None;self.played=[]
        self.setStyleSheet(STYLE)
    def run_job(self,title,function,callback=None,**kwargs):
        class Progress:
            def __call__(self,*args):pass
            def cancelled(self):return False
        result=function(self.library,Progress())
        if callback:callback(result)
    def play_file(self,file):self.played.append(file['id'])
    def reload_details(self,*args):pass


def settle(qapp):
    for _ in range(4):qapp.processEvents()


def cleanup(dialog,window,qapp):
    if dialog is not None:dialog.close()
    # exec() dialogs queue deletion in the outer event loop. Keep their test
    # parent alive while Qt destroys them, then explicitly dispose of the parent.
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);qapp.processEvents()
    window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    qapp.processEvents()


def assert_inside(button,dialog):
    point=button.mapTo(dialog,QPoint(0,0))
    assert point.y()>=0 and point.y()+button.height()<=dialog.height()
    assert point.x()>=0 and point.x()+button.width()<=dialog.width()


def test_long_file_names_keep_version_parameters_visible(qapp,library,video_factory):
    video=video_factory('ABC-123.'+'LongEdition.'*12+'2160p.HEVC.mp4')
    library.import_folder(video.parent,'movie',fast=True);work=library.query()[0]
    window=ToolWindow(library);dialog=show_versions(window,[work['id']])
    try:
        dialog.resize(850,500);settle(qapp)
        table=dialog.findChild(QTableWidget,'versionComparison')
        assert table.rowCount()==1 and table.columnWidth(0)<320
        assert table.columnViewportPosition(7)+table.columnWidth(7)<=table.viewport().width()
        assert table.item(0,0).text()==video.name and str(video) in table.item(0,0).toolTip()
        table.selectRow(0);settle(qapp)
        play=next(b for b in dialog.findChildren(QPushButton) if b.text()=='播放选中版本')
        play.click();assert window.played==[work['files'][0]['id']]
        prefer=next(b for b in dialog.findChildren(QPushButton) if b.text()=='设为默认版本')
        prefer.click();assert library.setting('preferred-file:'+str(work['id']))==work['files'][0]['id']
        menu=next(b.menu() for b in dialog.findChildren(QPushButton) if b.text()=='版本操作')
        assert menu.actions()[-2].isSeparator() and '仅移出' in menu.actions()[-1].text()
        for button in (play,prefer):assert_inside(button,dialog)
    finally:cleanup(dialog,window,qapp)


def test_vr_form_scrolls_while_save_stays_visible_in_short_large_font_window(qapp,library,tmp_path):
    window=ToolWindow(library);window.setStyleSheet(STYLE+'\n* {font-size: 18px;}')
    dialog=VrPresetDialog(window,tmp_path)
    try:
        dialog.show();dialog.resize(600,400);settle(qapp)
        assert dialog.height()==400
        scroll=dialog.findChild(QScrollArea,'vrPresetFields')
        assert scroll.verticalScrollBar().maximum()>0
        buttons=dialog.findChild(QDialogButtonBox)
        for role in (QDialogButtonBox.StandardButton.Save,QDialogButtonBox.StandardButton.Cancel):assert_inside(buttons.button(role),dialog)
        dialog.fields['fov'].setValue(75);buttons.button(QDialogButtonBox.StandardButton.Save).click()
        assert library.setting('vr_directory_presets')[0]['vr']['fov']==75
    finally:cleanup(dialog,window,qapp)


def test_organizer_settings_scroll_without_hiding_preview_or_execute(qapp,library,video_factory,tmp_path):
    library.import_folder(video_factory('ABC-456.mp4').parent,'movie',fast=True)
    window=ToolWindow(library);dialog=Organizer(window,library.query()[0]['id'])
    try:
        dialog.show();dialog.resize(760,460);settle(qapp)
        assert dialog.height()==460
        assert dialog.findChild(QScrollArea,'organizerSettings').verticalScrollBar().maximum()>0
        assert dialog.table.viewport().height()>=40
        for button in (dialog.preview,dialog.execute):assert_inside(button,dialog)
        dialog.target.setText(str(tmp_path/'out'));dialog.preview.click()
        assert dialog.execute.isEnabled() and dialog.table.rowCount()==1
    finally:cleanup(dialog,window,qapp)


def test_metadata_repair_labels_follow_actual_selected_scope(qapp,library,video_factory):
    for name,color in [('First.2023.mp4','blue'),('Second.2024.mp4','red')]:
        library.import_folder(video_factory(name,color=color).parent,'movie',fast=True)
    window=ToolWindow(library);dialog=show_metadata_health(window)
    try:
        table=dialog.findChild(QTableWidget,'metadataHealthTable');label=dialog.findChild(QLabel,'metadataRepairScope')
        assert table.rowCount()==2 and '全部 2 部' in label.text()
        table.selectRow(0)
        assert '选中的 1 部' in label.text()
        assert dialog.findChild(QPushButton,'repairMissingMetadata').text()=='补全选中 1 部'
        table.clearSelection();assert '全部 2 部' in label.text()
    finally:cleanup(dialog,window,qapp)


def test_naming_rule_labels_explain_shared_target_scope(qapp,library,tmp_path):
    window=ToolWindow(library);observed=[]
    def inspect():
        dialog=next(d for d in window.findChildren(QDialog) if d.isVisible())
        observed.append(dialog.findChild(QLabel,'namingRuleScope').text());dialog.reject()
    try:
        QTimer.singleShot(0,inspect);show_naming_rules(window,'movie',tmp_path)
        assert '目标目录规则' in observed[0] and '共用' in observed[0]
        QTimer.singleShot(0,inspect);show_naming_rules(window,'movie')
        assert observed[1]=='分类默认规则：电影'
    finally:cleanup(None,window,qapp)
