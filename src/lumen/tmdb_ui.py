"""Desktop setup for the bundled movie and series source."""
from pathlib import Path
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QLineEdit, QPushButton, QWidget

from . import tmdb


class TmdbSettings(QWidget):
    def __init__(self, library):
        super().__init__()
        config = tmdb.settings(library)
        form = QFormLayout(self)
        hint = QLabel('TMDB · 内置电影、电视剧和动漫刮削。保存令牌并启用后，可在详情页刮削和媒体库来源设置中选择 TMDB。动画电影使用电影库，连载动画使用电视剧库。')
        hint.setWordWrap(True)
        form.addRow(hint)

        self.token = QLineEdit(config.get('token', ''))
        self.token.setObjectName('tmdbReadToken')
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setMaxLength(4096)
        self.token.setPlaceholderText('粘贴 API Read Access Token')
        form.addRow('API 读取访问令牌', self.token)
        self.enabled = QCheckBox('启用 TMDB 刮削来源')
        self.enabled.setObjectName('tmdbEnabled')
        self.enabled.setChecked(bool(config.get('enabled')))
        form.addRow(self.enabled)

        help_button = QPushButton('打开 TMDB API 设置')
        help_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://www.themoviedb.org/settings/api')))
        form.addRow(help_button)
        privacy = QLabel('搜索与详情请求访问 api.themoviedb.org，图片访问 image.tmdb.org，沿用默认刮削代理。令牌随本机数据库保存，数据库备份也会包含它。')
        privacy.setWordWrap(True)
        form.addRow(privacy)

        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        logo = QLabel()
        logo.setAccessibleName('The Movie Database')
        logo.setPixmap(QIcon(str(root / 'assets' / 'tmdb-logo.svg')).pixmap(144, 20))
        form.addRow(logo)
        attribution = QLabel(tmdb.ATTRIBUTION)
        attribution.setWordWrap(True)
        form.addRow(attribution)

        save = QPushButton('保存 TMDB 设置')
        save.setObjectName('saveTmdbSettings')
        form.addRow(save)
        status = QLabel()
        status.setObjectName('tmdbStatus')
        status.setWordWrap(True)
        form.addRow(status)

        def persist():
            try:
                tmdb.save_settings(library, self.token.text(), self.enabled.isChecked())
            except ValueError as error:
                status.setText(str(error))
                return
            status.setText('已保存，可在刮削来源列表选择 TMDB。' if self.enabled.isChecked() else '已保存，TMDB 当前停用。')

        save.clicked.connect(persist)
