"""Host-owned network session editor, separate from plugin JavaScript config."""
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QComboBox,
    QLineEdit,QPushButton,QHBoxLayout)
from .plugins import Plugins
from .plugin_access import origin,session,save_session


def show_plugin_access(window,plugin_id):
    plugin=next((item for item in Plugins(window.library).installed() if item['id']==plugin_id),None)
    if not plugin:raise ValueError('请先安装来源')
    dialog=QDialog(window);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowTitle(plugin['name']+' · 站点访问设置');dialog.resize(650,450)
    layout=QVBoxLayout(dialog);form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    note=QLabel('JavBus / JavDB 默认使用浏览器兼容请求，按需启动短时进程。若站点仍要求登录或验证，可在同一代理出口的浏览器完成验证，并填写自己的站点会话。兼容请求不执行网页 JavaScript，也不能保证通过所有站点验证。');note.setWordWrap(True);layout.addWidget(note)
    base=plugin['config'].get('base_url','');value=session(window.library,plugin)
    host=QLabel(base);host.setWordWrap(True);form.addRow('会话绑定站点',host)
    mode=QComboBox();mode.setObjectName('siteTransport')
    for title,key in [('自动（JavBus / JavDB 优先兼容请求）','auto'),('浏览器兼容请求','browser'),('标准 curl / httpx 请求','standard')]:mode.addItem(title,key)
    mode.setCurrentIndex(max(0,mode.findData(value.get('transport','auto'))));form.addRow('请求模式',mode)
    cookie=QLineEdit(value.get('cookie','') if value.get('origin')==origin(base) else '')
    cookie.setObjectName('siteCookie');cookie.setEchoMode(QLineEdit.EchoMode.Password)
    cookie.setPlaceholderText('可选：只填写 Cookie 内容，不含 Cookie: 前缀');form.addRow('Cookie',cookie)
    agent=QLineEdit(value.get('user_agent','') if value.get('origin')==origin(base) else '')
    agent.setObjectName('siteUserAgent');agent.setPlaceholderText('可选：与取得 Cookie 的浏览器一致；留空由请求引擎设置');form.addRow('User-Agent',agent)
    layout.addLayout(form)
    hint=QLabel('会话只向绑定的协议、主机和端口发送，不转发给图片 CDN 或其他来源。Cookie 保存在本机数据库中，不传给插件脚本；数据库备份也会包含它。站点登录失效或网络出口变化后，可能需要更新。');hint.setWordWrap(True);layout.addWidget(hint)
    status=QLabel('保存后返回影片来源页面，用一个已知编号检测。');status.setWordWrap(True);status.setObjectName('siteAccessStatus');layout.addWidget(status);layout.addStretch()
    row=QHBoxLayout();layout.addLayout(row)
    browser=QPushButton('在浏览器打开站点');browser.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(base)) if origin(base) else None);row.addWidget(browser)
    clear=QPushButton('清除会话');row.addWidget(clear)
    save=QPushButton('保存');save.setObjectName('saveSiteAccess');row.addWidget(save)
    close=QPushButton('关闭');close.clicked.connect(dialog.close);row.addWidget(close)
    def persist(clear_session=False):
        values={'transport':mode.currentData(),'cookie':'' if clear_session else cookie.text(),'user_agent':'' if clear_session else agent.text()}
        try:save_session(window.library,plugin,values)
        except ValueError as error:status.setText(str(error));return
        if clear_session:cookie.clear();agent.clear()
        status.setText('已清除会话。' if clear_session else '已保存。请返回来源检测；浏览器与 Lumen 的代理应使用相同出口。')
    save.clicked.connect(lambda:persist());clear.clicked.connect(lambda:persist(True))
    dialog.show();return dialog
