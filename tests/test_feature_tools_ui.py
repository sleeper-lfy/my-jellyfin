from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QPushButton,QTableWidget
from lumen.ui import MainWindow


def test_all_new_feature_entrypoints_open_with_real_library(qapp,tmp_path,video_factory):
    window=MainWindow(tmp_path/'data')
    try:
        window.library.import_folder(video_factory('Features.2024.mp4').parent,'movie',fast=True)
        identifier=window.library.query()[0]['id'];window.navigate('movie');window.open_details(identifier,fetch=False)
        # Run actual feature read jobs immediately to exercise all integration signatures.
        class Progress:
            def __call__(self,*args):pass
            def cancelled(self):return False
        def run(title,function,callback=None,**kwargs):
            result=function(window.library,Progress())
            if callback:callback(result)
        window.run_job=run
        sources=window.numbered_sources();assert sources.isVisible();sources.close()
        health=window.metadata_health();assert health.isVisible() and health.findChild(QTableWidget);health.close()
        versions=window.compare_versions([identifier]);assert versions.isVisible() and versions.findChild(QTableWidget).rowCount()==1
        versions.findChild(QTableWidget).selectRow(0)
        played=[];window.player.open_file=lambda file:played.append(file['id']);window.random_active=True
        next(button for button in versions.findChildren(QPushButton) if button.text()=='播放选中版本').click()
        assert played and not window.random_active
        versions.close()
        duplicates=window.duplicate_versions();assert duplicates.isVisible();duplicates.close()
        organizer=window.detail_page.organize();assert organizer.isVisible();organizer.close()
        def close_export():
            dialog=next(dialog for dialog in window.findChildren(QDialog) if dialog.isVisible() and 'NFO' in dialog.windowTitle())
            assert any('导出' in button.text() for button in dialog.findChildren(QPushButton));dialog.reject()
        QTimer.singleShot(0,close_export);window.export_nfo([identifier])
        actions=[action.text() for group in window.detail_page.management_menu.actions() for action in (group.menu().actions() if group.menu() else [group])]
        assert '版本对比 / 默认播放…' in actions and '导出 NFO 与图片…' in actions
    finally:window.close()
