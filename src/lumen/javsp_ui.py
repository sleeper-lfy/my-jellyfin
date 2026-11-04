"""Explicit local engine setup; all engine imports execute off the UI thread."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QLineEdit,QPushButton,QFileDialog,QCheckBox,QPlainTextEdit)
from .plugins import Plugins
from .javsp_bridge import settings,validate_settings,probe,ID
from .core import ImportCancelled


def show_javsp_settings(window,on_saved=None):
    previous=getattr(window,'javsp_settings_dialog',None)
    if previous is not None:
        previous.show();previous.raise_();previous.activateWindow();return previous
    dialog=QDialog(window);dialog.setWindowTitle('JavSP · 本地辅助刮削');dialog.resize(720,560)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);window.javsp_settings_dialog=dialog
    dialog.finished.connect(lambda _:setattr(window,'javsp_settings_dialog',None))
    layout=QVBoxLayout(dialog)
    note=QLabel('使用你单独安装并信任的 JavSP 源码与 Python 环境。只按编号调用抓取器，不启动 JavSP 的目录扫描、文件整理或自动更新。站点请求及代理由 JavSP config.yml 管理；补图仍使用 Lumen 的精确域名权限。');note.setWordWrap(True);layout.addWidget(note)
    link=QLabel('<a href="https://github.com/Yuukiy/JavSP">JavSP 项目与安装说明</a>');link.setOpenExternalLinks(True);layout.addWidget(link)
    form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);layout.addLayout(form)
    value=settings(window.library);fields={}
    for key,label,directory in [('python','独立环境 Python',False),('root','JavSP 源码目录',True),('config','config.yml（可留空）',False)]:
        edit=QLineEdit(str(value.get(key,'')));edit.setObjectName('javsp_'+key);fields[key]=edit
        row=QHBoxLayout();row.addWidget(edit,1);browse=QPushButton('浏览…');row.addWidget(browse);form.addRow(label,row)
        def choose(checked=False,field=edit,is_directory=directory):
            path=QFileDialog.getExistingDirectory(dialog,'选择 JavSP 源码目录',field.text()) if is_directory else QFileDialog.getOpenFileName(dialog,'选择文件',field.text())[0]
            if path:field.setText(path)
        browse.clicked.connect(choose)
    hosts=QLineEdit(', '.join(value.get('image_domains',[])));hosts.setObjectName('javsp_image_domains');hosts.setPlaceholderText('例如 images.example.com, cdn.example.com');form.addRow('额外补图域名',hosts)
    manifest=json.loads((Plugins.builtin_numbered_plugin(ID)/'manifest.json').read_text(encoding='utf-8'))
    permissions=QLabel('默认补图主机：'+', '.join(manifest['domains'])+'。此设置仅约束 Lumen 下载图片；JavSP 抓取器使用其自身网络配置。');permissions.setWordWrap(True);layout.addWidget(permissions)
    enabled=QCheckBox('保存后启用 JavSP 来源');enabled.setChecked(window.library.setting('plugin:'+ID,{}).get('enabled',False));enabled.setObjectName('javsp_enabled');layout.addWidget(enabled)
    status=QPlainTextEdit();status.setReadOnly(True);status.setObjectName('javsp_status');status.setPlainText('先检测环境，再保存。环境检测不访问刮削站点；真实编号检测请返回影片来源页面。');layout.addWidget(status,1)
    actions=QHBoxLayout();layout.addLayout(actions)
    test=QPushButton('检测环境');test.setObjectName('javsp_probe');save=QPushButton('检测并保存');save.setObjectName('javsp_save');close=QPushButton('关闭');close.clicked.connect(dialog.close)
    for button in (test,save,close):actions.addWidget(button)
    def execute(persist):
        try:config=validate_settings({**{key:field.text().strip() for key,field in fields.items()},'image_domains':[host.strip() for host in hosts.text().replace('，',',').split(',') if host.strip()]})
        except ValueError as error:status.setPlainText(str(error));return
        should_enable=enabled.isChecked();test.setEnabled(False);save.setEnabled(False);status.setPlainText('正在独立进程中检测 JavSP 配置与依赖…')
        def run(library,progress):
            try:
                result=probe(library,config,progress.cancelled)
                if not result.get('ready'):raise ValueError('JavSP 环境未就绪')
                if persist:
                    manager=Plugins(library);manager.update_builtin_numbered_plugin(ID)
                    library.set_setting('javsp',config);manager.configure(ID,{'enabled':should_enable})
                return {'ok':True,'sources':result['sources']}
            except ImportCancelled:return {'ok':False,'message':'检测已停止，未保存。'}
            except Exception as error:return {'ok':False,'message':str(error)}
        def done(result):
            if window.javsp_settings_dialog is not dialog:return
            test.setEnabled(True);save.setEnabled(True)
            if not result['ok']:status.setPlainText(result['message']);return
            status.setPlainText(('已保存。' if persist else '环境可用。')+'\n配置来源：'+json.dumps(result['sources'],ensure_ascii=False)+'\n可在分类默认规则中选择 JavSP 为首选或备用来源，电影与 VR 均可使用。')
            if persist and on_saved:on_saved()
        window.run_job('检测 JavSP 环境',run,done)
    test.clicked.connect(lambda:execute(False));save.clicked.connect(lambda:execute(True))
    dialog.show();return dialog
