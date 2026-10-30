"""Explicit portrait matching; all provider and image work runs off the GUI thread."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLineEdit,QComboBox,QCheckBox,QPushButton,QLabel,QInputDialog
from .plugins import Plugins


def show_actor_scraper(window,name=''):
    existing=getattr(window,'actor_photo_dialog',None)
    if existing is not None:
        existing.raise_();existing.activateWindow();return existing
    dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowTitle('刮削演员头像');dialog.resize(520,330)
    window.actor_photo_dialog=dialog
    dialog.destroyed.connect(lambda:setattr(window,'actor_photo_dialog',None))
    layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
    actor=QLineEdit(name);actor.setObjectName('actorPhotoName');actor.setPlaceholderText('输入本地演员姓名')
    source=QComboBox();source.setObjectName('actorPhotoSource')
    replace=QCheckBox('覆盖已有头像（默认只补充缺失头像）')
    form.addRow('演员姓名',actor);form.addRow('头像来源',source);form.addRow(replace)
    status=QLabel('搜索后点击正确的头像或姓名，更新该演员关联作品。已锁定的演员资料会保留。');status.setWordWrap(True);layout.addWidget(status)
    search=QPushButton('搜索演员头像');search.setObjectName('searchActorPhoto');layout.addWidget(search)
    install=QPushButton('安装 / 更新内置头像来源…');layout.addWidget(install)
    batch=QPushButton('批量自动获取演员头像…');layout.addWidget(batch)
    def open_batch():
        from .actor_batch_ui import show_actor_batch
        show_actor_batch(window)
    batch.clicked.connect(open_batch)
    def reload_sources():
        selected=source.currentData();source.clear()
        for plugin in Plugins(window.library).installed():
            if plugin['config'].get('enabled') and 'actors' in plugin['capabilities']:source.addItem(plugin['name'],plugin['id'])
        if selected is not None:source.setCurrentIndex(max(0,source.findData(selected)))
        search.setEnabled(source.count()>0)
        if not source.count():status.setText('请先安装并启用头像来源；也可在设置中安装支持 actors 的第三方插件。')
    def setup_source():
        sources=[('TVmaze · 电视剧演员（api.tvmaze.com / static.tvmaze.com）','tvmaze'),
                 ('Wikimedia · 人物照片（www.wikidata.org / commons.wikimedia.org / upload.wikimedia.org）','wikimedia-actors'),
                 ('JavRate · AV 女优头像（r.jina.ai / www.javrate.com / picture.avking.xyz）','javrate-actors'),
                 ('JavDB · AV 女优头像（javdb.com / c0.jdbstatic.com）','javdb-actors'),
                 ('JavBus · AV 女优头像（www.javbus.com / javbus.com / r.jina.ai）','javbus-actors')]
        options=[label for label,_ in sources]
        choice,ok=QInputDialog.getItem(dialog,'安装 / 更新并启用头像来源','来源及其网络主机权限',options,0,False)
        if not ok:return
        plugin_id=next(plugin_id for label,plugin_id in sources if label==choice)
        def update(library,progress):
            manager=Plugins(library);manager.update_builtin_actor_plugin(plugin_id);manager.configure(plugin_id,{'enabled':True})
            return {'updated':1}
        window.run_job('安装头像来源',update,lambda _:reload_sources() if window.actor_photo_dialog is dialog else None)
    install.clicked.connect(setup_source)
    def search_actor():
        name=actor.text().strip();plugin_id=source.currentData();overwrite=replace.isChecked()
        if not name or not plugin_id:status.setText('请输入本地演员姓名并选择头像来源。');return
        def complete(records):
            if window.actor_photo_dialog is not dialog:return
            if not records:status.setText('未找到有头像的匹配资料，可更换来源或尝试别名。');return
            from .matching import CandidatePicker
            display=[{**record,'title':record['name'],'poster':record.get('photo')} for record in records if record.get('photo')]
            if not display:status.setText('来源找到了演员，但没有提供头像。');return
            picker=CandidatePicker(window.library.directory,plugin_id,display,dialog)
            picker.setWindowTitle('选择演员头像 · 点击后更新')
            picker.layout().itemAt(0).widget().setText('确认姓名和头像后点击候选；只更新本地演员头像，不修改影片标题。')
            for i,record in enumerate(display):picker.items.item(i).setText(record['name']+'\n'+(' / '.join(record.get('aliases',[])[:3])))
            accepted=picker.exec();candidate=picker.selection();picker.deleteLater()
            if not accepted or candidate is None:return
            def saved(result):
                window.status.setText(f"演员头像：更新 {result['updated']} 部 · 跳过 {result['skipped']} 部")
                if window.detail_page is not None:window.reload_details(window.detail_page.work_id)
                if window.actor_photo_dialog is dialog:dialog.close()
            window.run_job('保存演员头像',lambda library,progress:Plugins(library).merge_actor(plugin_id,candidate,name,replace=overwrite),saved)
        status.setText('正在后台搜索，可继续使用主界面。')
        window.run_job('搜索演员头像',lambda library,progress:Plugins(library).run(plugin_id,'actors',query=name),complete)
    search.clicked.connect(search_actor);reload_sources();dialog.show();return dialog
