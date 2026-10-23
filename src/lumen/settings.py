import json
from pathlib import Path
import sqlite3
import time
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget, QWidget, QLineEdit,
 QComboBox, QCheckBox, QSpinBox, QListWidget, QFileDialog, QMessageBox, QPlainTextEdit)
from .core import tool
from .plugins import Plugins
from .ui import button, label, KINDS


class Settings(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.library = window, window.library
        self.manager = Plugins(self.library)
        self.setWindowTitle('设置 · Lumen')
        self.resize(820, 720)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        general = QWidget()
        form = QFormLayout(general)
        self.proxy = QLineEdit(self.library.setting('proxy', ''))
        self.proxy.setPlaceholderText('留空直连；http://127.0.0.1:7890 或 socks5://127.0.0.1:1080')
        form.addRow('默认刮削代理', self.proxy)
        form.addRow('数据目录', label(str(self.library.directory)))
        form.addRow('FFmpeg', label(tool('ffmpeg') or '未安装；请将 ffmpeg.exe / ffprobe.exe 所在目录加入 PATH'))
        form.addRow('FFprobe', label(tool('ffprobe') or '未安装'))
        form.addRow(button('保存默认代理', self.save_proxy, True))
        form.addRow(button('备份本地数据库…', self.backup))
        form.addRow(button('恢复数据库备份…', self.restore))
        note = label('备份包含资料、评分、队列和历史，不包含视频、图片缓存及插件。\n完整迁移请同时备份数据目录及原视频目录。恢复前自动保留当前数据库副本。')
        note.setWordWrap(True)
        form.addRow(note)
        tabs.addTab(general, '通用 / 数据安全')
        plugins = QWidget()
        layout = QVBoxLayout(plugins)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.list.currentRowChanged.connect(self.select_plugin)
        controls = QHBoxLayout()
        controls.addWidget(button('安装插件文件夹…', self.install))
        controls.addWidget(button('卸载选中插件', self.uninstall))
        layout.addLayout(controls)
        self.description = label('安装前请查看插件权限。脚本只处理网络响应，不具有文件操作接口。')
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        config = QFormLayout()
        self.enabled = QCheckBox('启用插件')
        self.base = QLineEdit()
        self.category = QLineEdit()
        self.category.setPlaceholderText('分类路径；多个分类可用逗号分隔')
        self.plugin_proxy = QLineEdit()
        self.plugin_proxy.setPlaceholderText('inherit 跟随默认；留空直连；也可单独填写代理地址')
        self.priority = QSpinBox()
        self.priority.setRange(0, 999)
        self.interval = QSpinBox()
        self.interval.setRange(1, 720)
        self.auto = QCheckBox('程序运行期间定期发现新片')
        for title, widget in [('状态', self.enabled),('站点地址', self.base),('分类路径', self.category),('独立代理', self.plugin_proxy),('优先级（越小越优先）', self.priority),('间隔（小时）', self.interval),('',self.auto)]:
            config.addRow(title, widget)
        layout.addLayout(config)
        layout.addWidget(button('保存插件配置', self.save_plugin, True))
        tabs.addTab(plugins, '第三方插件')
        partitions = QWidget()
        partition_layout = QFormLayout(partitions)
        self.partition_controls = {}
        for kind in ['movie', 'series']:
            box = QComboBox()
            box.addItem('手动刮削（默认）', '')
            for p in self.manager.installed():
                if 'search' in p['capabilities']:
                    box.addItem(p['name'], p['id'])
            previous = self.library.setting('partition:' + kind, {})
            box.setCurrentIndex(max(0, box.findData(previous.get('plugin', ''))))
            destination = QLineEdit(previous.get('destination', ''))
            destination.setPlaceholderText('留空仅导入；设置后，唯一匹配成功将自动整理至此目录')
            row = QHBoxLayout()
            row.addWidget(destination)
            row.addWidget(button('浏览', lambda checked=False, field=destination: self.choose_folder(field)))
            partition_layout.addRow(KINDS[kind] + ' · 自动刮削', box)
            partition_layout.addRow('自动整理目标', row)
            self.partition_controls[kind] = (box, destination)
        notice = label('自动整理仅在标题、年份和类型唯一匹配后执行。\n目标存在同名文件时停止，复制校验成功后才删除原文件；失败可从任务页恢复。\n“其他”保持目录结构且不联网，可在详情页手动整理。')
        notice.setWordWrap(True)
        partition_layout.addRow(notice)
        partition_layout.addRow(button('保存分区规则', self.save_partitions, True))
        tabs.addTab(partitions, '导入 / 分区规则')
        downloads = QWidget()
        download_form = QFormLayout(downloads)
        from .downloads import default_download_root
        download_config = self.library.setting('downloads', {})
        self.download_paths = {}
        for kind in ['movie','series','vr']:
            field = QLineEdit(str(default_download_root(self.library,kind)))
            row = QHBoxLayout();row.addWidget(field)
            row.addWidget(button('浏览',lambda checked=False,field=field:self.choose_folder(field)))
            download_form.addRow(KINDS[kind]+'默认目录',row);self.download_paths[kind]=field
        self.magnet_client=QComboBox()
        for title,value in [('自动（优先 qBittorrent）','auto'),('qBittorrent（传入保存目录）','qbittorrent'),('系统关联下载器（目录需在下载器选择）','system'),('自定义支持目录参数的下载器','custom')]:self.magnet_client.addItem(title,value)
        self.magnet_client.setCurrentIndex(max(0,self.magnet_client.findData(download_config.get('magnet_client','auto'))))
        download_form.addRow('磁力下载工具',self.magnet_client)
        self.magnet_executable=QLineEdit(download_config.get('magnet_executable',''))
        self.magnet_executable.setPlaceholderText('留空自动寻找 qBittorrent；自定义工具须指定程序路径')
        executable_row=QHBoxLayout();executable_row.addWidget(self.magnet_executable)
        def choose_executable():
            path,_=QFileDialog.getOpenFileName(self,'选择下载器程序',self.magnet_executable.text())
            if path:self.magnet_executable.setText(path)
        executable_row.addWidget(button('选择程序',choose_executable));download_form.addRow('下载器程序',executable_row)
        self.magnet_arguments=QLineEdit(json.dumps(download_config.get('magnet_arguments',['--save-path={directory}','{url}']),ensure_ascii=False))
        download_form.addRow('自定义参数（JSON 数组）',self.magnet_arguments)
        download_notice=label('每部作品保存到所属分类的默认目录下，可在详情中单独更改。HTTP 直链完成后自动入库并保留当前影视资料。\nqBittorrent 可接收保存目录；系统 magnet 通用协议无法保证迅雷等工具的保存位置，需在下载器内选择。外部下载完成后点击详情中的“检查下载文件并入库”。')
        download_notice.setWordWrap(True);download_form.addRow(download_notice)
        download_form.addRow(button('保存下载设置',self.save_downloads,True));tabs.addTab(downloads,'下载')
        lan = QWidget()
        lan_form = QFormLayout(lan)
        from .server import ensure_token,local_addresses
        configuration = self.library.setting('lan', {})
        self.lan_enabled = QCheckBox('允许局域网 Android 客户端连接')
        self.lan_enabled.setChecked(bool(window.lan_server))
        self.lan_port = QSpinBox()
        self.lan_port.setRange(1024,65535)
        self.lan_port.setValue(configuration.get('port',8097))
        self.lan_key = QLineEdit(ensure_token(self.library))
        self.lan_key.setReadOnly(True)
        self.lan_key.setEchoMode(QLineEdit.EchoMode.Password)
        lan_form.addRow('服务', self.lan_enabled)
        lan_form.addRow('端口', self.lan_port)
        lan_form.addRow('访问密钥', self.lan_key)
        key_actions = QHBoxLayout()
        def copy_key():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.lan_key.text())
        key_actions.addWidget(button('复制密钥', copy_key))
        key_actions.addWidget(button('显示 / 隐藏', lambda: self.lan_key.setEchoMode(QLineEdit.EchoMode.Normal if self.lan_key.echoMode()==QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password)))
        lan_form.addRow(key_actions)
        addresses = label('')
        addresses.setWordWrap(True)
        def refresh_addresses():
            addresses.setText('\n'.join('http://' + address + ':' + str(self.lan_port.value()) for address in local_addresses() if address != '127.0.0.1') or '请在 Windows 网络设置中查看电脑的局域网 IPv4 地址。')
        refresh_addresses()
        self.lan_port.valueChanged.connect(refresh_addresses)
        lan_form.addRow('电脑地址', addresses)
        explanation = label('手机与电脑连接同一局域网，在 Android 客户端发现或输入电脑地址，并填写访问密钥。\n自动发现需要允许专用网络的 UDP 8098，视频连接使用上方 TCP 端口。\n如 Windows 防火墙提示，请仅允许专用网络。服务仅在程序打开时运行；视频原格式直传，不进行转码。')
        explanation.setWordWrap(True)
        lan_form.addRow(explanation)
        def save_lan():
            try:
                window.apply_lan(self.lan_enabled.isChecked(),self.lan_port.value())
                QMessageBox.information(self,'局域网服务','已启动' if window.lan_server else '已停止')
            except Exception as exc:
                QMessageBox.warning(self,'无法启动局域网服务',str(exc))
        lan_form.addRow(button('应用局域网设置', save_lan, True))
        tabs.addTab(lan,'局域网 / Android')
        outer.addWidget(button('关闭', self.accept))
        self.reload()

    def save_downloads(self):
        try:
            values={kind:field.text().strip() for kind,field in self.download_paths.items()}
            if any(not value or not Path(value).expanduser().is_absolute() for value in values.values()):raise ValueError('请选择完整的默认下载目录')
            arguments=json.loads(self.magnet_arguments.text())
            if not isinstance(arguments,list) or any(not isinstance(arg,str) for arg in arguments):raise ValueError('下载器参数须为 JSON 字符串数组')
            if self.magnet_client.currentData()=='custom' and not self.magnet_executable.text().strip():raise ValueError('请选择自定义下载器程序')
            if self.magnet_client.currentData()=='custom' and (not any('{url}' in arg for arg in arguments) or not any('{directory}' in arg for arg in arguments)):
                raise ValueError('自定义参数必须同时包含 {url} 和 {directory}')
            self.library.set_setting('downloads',{**values,'magnet_client':self.magnet_client.currentData(),
                'magnet_executable':self.magnet_executable.text().strip(),'magnet_arguments':arguments})
            QMessageBox.information(self,'下载设置','默认目录和下载器已保存。')
        except (ValueError,TypeError) as error:QMessageBox.warning(self,'未保存下载设置',str(error))

    def choose_folder(self, field):
        path = QFileDialog.getExistingDirectory(self, '选择目标目录')
        if path:
            field.setText(path)

    def save_proxy(self):
        self.library.set_setting('proxy', self.proxy.text().strip())
        QMessageBox.information(self, '已保存', '默认刮削代理已保存。')

    def reload(self):
        self.plugins = self.manager.installed()
        self.list.clear()
        for p in self.plugins:
            self.list.addItem(f"{'●' if p['config'].get('enabled') else '○'} {p['name']}  ·  {p['version']}")
        if self.plugins:
            self.list.setCurrentRow(0)

    def select_plugin(self, index):
        if index < 0 or index >= len(self.plugins):
            return
        p = self.plugins[index]
        c = p['config']
        self.description.setText(f"{p.get('description', '')}\n能力：{', '.join(p['capabilities'])}\n允许访问：{', '.join(p['domains'])}\n权限：网络只读 GET；无文件读写；脚本超时 8 秒。")
        self.enabled.setChecked(c.get('enabled', False))
        self.base.setText(c.get('base_url', ''))
        self.category.setText(c.get('category', ''))
        self.plugin_proxy.setText(c.get('proxy', 'inherit'))
        self.priority.setValue(c.get('priority', 100))
        self.interval.setValue(c.get('interval_hours', 24))
        self.auto.setChecked(c.get('auto_refresh', False))

    def save_plugin(self):
        index = self.list.currentRow()
        if index < 0:
            return
        p = self.plugins[index]
        self.manager.configure(p['id'], {'enabled':self.enabled.isChecked(), 'base_url':self.base.text().strip(),
          'category':self.category.text().strip(), 'proxy':self.plugin_proxy.text().strip(), 'priority':self.priority.value(),
          'interval_hours':self.interval.value(), 'auto_refresh':self.auto.isChecked()})
        self.reload()

    def install(self):
        folder = QFileDialog.getExistingDirectory(self, '选择包含 manifest.json 和 plugin.js 的文件夹')
        if not folder:
            return
        try:
            manifest = json.loads((Path(folder) / 'manifest.json').read_text(encoding='utf-8'))
            if QMessageBox.question(self, '插件网络权限', f"安装 {manifest['name']}？\n允许请求：{', '.join(manifest['domains'])}\n安装后默认禁用，可在配置页启用。") != QMessageBox.StandardButton.Yes:
                return
            self.manager.install(folder)
            self.reload()
        except Exception as exc:
            QMessageBox.warning(self, '安装失败', str(exc))

    def uninstall(self):
        index = self.list.currentRow()
        if index >= 0 and QMessageBox.question(self, '卸载插件', '删除此插件脚本及配置？已刮削的影片资料会保留。') == QMessageBox.StandardButton.Yes:
            self.manager.uninstall(self.plugins[index]['id'])
            self.reload()

    def save_partitions(self):
        if any(destination.text().strip() for _, destination in self.partition_controls.values()):
            if QMessageBox.question(self, '启用自动文件整理', '导入并唯一匹配后，将自动移动视频及关联字幕到配置目录。是否保存这些规则？') != QMessageBox.StandardButton.Yes:
                return
        for kind, (box, destination) in self.partition_controls.items():
            self.library.set_setting('partition:' + kind, {'plugin':box.currentData(), 'destination':destination.text().strip()})
        QMessageBox.information(self, '已保存', '分区规则已保存。')

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, '备份数据库', f'lumen-{int(time.time())}.sqlite', 'SQLite (*.sqlite)')
        if path:
            try:
                self.library.backup(path)
                QMessageBox.information(self, '备份完成', path)
            except Exception as exc:
                QMessageBox.warning(self, '备份失败', str(exc))

    def restore(self):
        if self.window.lan_server:
            QMessageBox.information(self, "局域网服务正在运行", "请先在局域网 / Android 设置中关闭服务，再恢复数据库，以免手机播放记录写入恢复中的数据库。")
            return
        if any(j.isRunning() for j in self.window.jobs):
            QMessageBox.information(self, '任务进行中', '请等待后台任务结束后再恢复。')
            return
        path, _ = QFileDialog.getOpenFileName(self, '选择数据库备份', '', 'SQLite (*.sqlite)')
        if not path:
            return
        if QMessageBox.question(self, '恢复备份', '将恢复备份中的媒体资料、评分、历史和队列。当前数据库会先自动备份，视频文件不受影响。继续？') != QMessageBox.StandardButton.Yes:
            return
        try:
            from .backup import restore_database
            self.window.player.finish()
            restore_database(self.library, path)
            self.window.random_active = False
            self.accept()
            self.window.navigate('home')
        except Exception as exc:
            QMessageBox.warning(self, '恢复失败', str(exc))
