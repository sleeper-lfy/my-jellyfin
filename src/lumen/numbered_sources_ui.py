"""Install numbered-film providers and inspect their live availability."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,
    QLineEdit,QPushButton,QMessageBox,QPlainTextEdit)
from .plugins import Plugins
from .core import ImportCancelled
from .numbered_sources import check_source


def show_numbered_providers(window):
    previous=getattr(window,'numbered_sources_dialog',None)
    if previous is not None:
        previous.show();previous.raise_();previous.activateWindow();return previous
    dialog=QDialog(window);dialog.setWindowTitle('影片来源 · 安装与检测');dialog.resize(650,450)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);window.numbered_sources_dialog=dialog
    dialog.finished.connect(lambda _:setattr(window,'numbered_sources_dialog',None))
    layout=QVBoxLayout(dialog)
    note=QLabel('影片来源用于编号搜索和完整资料。这里安装来源并检查是否可用；自动入库的首选、备用顺序与整理目标统一在分类默认规则中设置。');note.setWordWrap(True);layout.addWidget(note)
    install_row=QHBoxLayout();layout.addLayout(install_row)
    shipped=QComboBox();shipped.addItem('JavBus · 编号影片资料','javbus-films');shipped.addItem('JavDB · 编号影片资料','javdb-films');install_row.addWidget(shipped,1)
    install=QPushButton('安装 / 更新并启用…');install_row.addWidget(install)
    javsp=QPushButton('接入 JavSP 本地辅助引擎…');javsp.setObjectName('configureJavSP');layout.addWidget(javsp)
    configure=QPushButton('配置自动入库默认规则…');configure.setObjectName('configureIngestionDefaults');layout.addWidget(configure)
    def defaults():
        from .media_management_ui import show_media_management
        dialog.close();show_media_management(window,'sources')
    configure.clicked.connect(defaults)
    form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);layout.addLayout(form)
    source=QComboBox();source.setObjectName('providerToCheck');form.addRow('检测来源',source)
    query=QLineEdit();query.setPlaceholderText('输入一个已知影片编号');query.setObjectName('providerCheckCode');form.addRow('影片编号',query)
    status=QPlainTextEdit();status.setReadOnly(True);status.setObjectName('providerCheckResult');status.setPlainText('尚未检测。检测会真实请求来源，不修改影片资料。');layout.addWidget(status,1)
    actions=QHBoxLayout();layout.addLayout(actions)
    test=QPushButton('检测来源');test.setObjectName('primary');actions.addWidget(test);actions.addStretch()
    access=QPushButton('站点访问设置…');access.setObjectName('providerAccessSettings');actions.addWidget(access)
    close=QPushButton('关闭');close.clicked.connect(dialog.close);actions.addWidget(close)
    def reload():
        selected=source.currentData();source.clear()
        providers=[item for item in Plugins(window.library).installed() if item['config'].get('enabled') and 'search' in item['capabilities'] and 'detail' in item['capabilities']]
        for item in providers:source.addItem(item['name'],item['id'])
        source.setCurrentIndex(max(0,source.findData(selected)));test.setEnabled(bool(providers))
        access.setEnabled(bool(providers))
        if not providers:status.setPlainText('尚无已启用的影片来源。安装并启用来源后，可输入编号检测。')
    def install_source():
        identifier=shipped.currentData();folder=Plugins.builtin_numbered_plugin(identifier)
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        domains='\n'.join(manifest['domains'])
        if QMessageBox.question(dialog,'安装并启用影片来源',manifest['name']+'\n允许请求以下主机：\n'+domains+'\n\n是否安装 / 更新并启用？')!=QMessageBox.StandardButton.Yes:return
        def update(library,progress):
            manager=Plugins(library);manager.update_builtin_numbered_plugin(identifier);manager.configure(identifier,{'enabled':True});return {'installed':identifier}
        window.run_job('安装编号影片来源',update,lambda _:reload() if window.numbered_sources_dialog is dialog else None)
    def test_source():
        identifier=source.currentData();code=query.text().strip()
        if not identifier or not code:status.setPlainText('请选择来源并输入一个已知影片编号。');return
        test.setEnabled(False);status.setPlainText('正在后台检查搜索与详情解析…')
        def run(library,progress):
            try:return check_source(library,identifier,code,progress.cancelled)
            except ImportCancelled:return {'state':'failed','message':'检测已停止，可重新检测。'}
            except Exception as error:return {'state':'failed','message':str(error)}
        def done(value):
            if window.numbered_sources_dialog is not dialog:return
            test.setEnabled(True)
            names={'available':'可用','no_unique_match':'站点已响应，但此编号无唯一匹配','failed':'检测失败'}
            status.setPlainText(names.get(value['state'],value['state'])+'：'+value['message'])
        window.run_job('检测编号影片来源',run,done)
    install.clicked.connect(install_source);test.clicked.connect(test_source);query.returnPressed.connect(lambda:test.click() if test.isEnabled() else None)
    def configure_javsp():
        from .javsp_ui import show_javsp_settings
        show_javsp_settings(window,lambda:reload() if window.numbered_sources_dialog is dialog else None)
    javsp.clicked.connect(configure_javsp)
    def configure_access():
        from .plugin_access_ui import show_plugin_access
        if source.currentData():show_plugin_access(window,source.currentData())
    access.clicked.connect(configure_access)
    reload();dialog.show();return dialog
