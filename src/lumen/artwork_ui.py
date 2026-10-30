"""User-selected artwork, kept separately from scraper-owned metadata."""
import uuid
import json
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                              QDialogButtonBox)


def artwork_paths(library, work):
    from .artwork import still_paths
    selected = library.setting(f'artwork_{work["id"]}', {})
    paths = [selected.get('poster'), selected.get('thumbnail'), work.get('thumbnail')]
    for file in work['files']:
        paths.append(work['metadata'].get('nfo_thumbnails', {}).get(str(file['id'])))
        paths.append(str(library.directory / 'cache' / (file['digest'] + '.jpg')))
    paths.extend(still_paths(work))
    return list(dict.fromkeys(str(path) for path in paths if path and Path(path).is_file()))


def crop_image(image, role, anchor='center'):
    """Use the same crop for the preview and saved image."""
    if image.isNull():
        raise ValueError('图片无法读取，请选择其他图片')
    if role not in {'poster', 'thumbnail'} or anchor not in {'left', 'center', 'right'}:
        raise ValueError('无效的图片用途或裁切位置')
    ratio = 2 / 3 if role == 'poster' else 16 / 9
    width, height = image.width(), image.height()
    crop_width, crop_height = min(width, max(1, round(height * ratio))), min(height, max(1, round(width / ratio)))
    x = {'left': 0, 'center': (width - crop_width) // 2, 'right': width - crop_width}[anchor]
    return image.copy(x, (height - crop_height) // 2, crop_width, crop_height)


def save_artwork(library, work_id, path, role, anchor):
    from .images import decode
    library.work(work_id)
    image = crop_image(decode(str(path), QSize(4096, 4096)), role, anchor)
    folder = library.directory / 'cache' / 'artwork'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (uuid.uuid4().hex + '.jpg')
    if not image.save(str(target), 'JPEG', 95):
        raise ValueError('无法保存图片，原封面保留')
    try:
        with library.db:
            library.db.execute('BEGIN IMMEDIATE')
            library.work(work_id)
            selected = library.setting(f'artwork_{work_id}', {})
            selected[role] = str(target)
            library.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',
                               (f'artwork_{work_id}', json.dumps(selected, ensure_ascii=False)))
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {'updated': True}


class ArtworkDialog(QDialog):
    def __init__(self, window, work, path=None):
        super().__init__(window)
        self.setWindowTitle('选择海报 / 缩略图'); self.resize(640, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('选择图片与用途，再选择保留的区域。原图会保留。'))
        self.sources = QComboBox(); self.sources.setObjectName('artworkSource')
        self.sources.setMinimumContentsLength(30)
        self.sources.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        for index, source in enumerate(artwork_paths(window.library, work)):
            self.sources.addItem(f'{index + 1} · {Path(source).name}', source)
        if path:
            self.sources.setCurrentIndex(max(0, self.sources.findData(path)))
        layout.addWidget(self.sources)
        row = QHBoxLayout(); layout.addLayout(row)
        self.role = QComboBox(); self.role.addItem('设为海报（2:3）', 'poster'); self.role.addItem('设为缩略图（16:9）', 'thumbnail'); row.addWidget(self.role)
        self.anchor = QComboBox()
        for title, key in [('居中', 'center'), ('靠左', 'left'), ('靠右', 'right')]: self.anchor.addItem(title, key)
        row.addWidget(self.anchor)
        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumSize(400, 360); layout.addWidget(self.preview, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
        for control in (self.sources, self.role, self.anchor): control.currentIndexChanged.connect(self.render)
        from .images import image_cache
        image_cache().changed.connect(self.render)
        self.render()

    def render(self):
        from .images import image_cache
        from PySide6.QtGui import QPixmap
        cache=image_cache();path=self.sources.currentData()
        picture = cache.request(path, QSize(960, 720))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(not picture.isNull())
        if picture.isNull():
            failed=any(key[0]==path and image.isNull() and key not in cache.pending for key,image in cache.cache.items())
            self.preview.clear()
            self.preview.setText('图片无法读取，请选择其他图片' if failed else '正在加载图片…' if self.sources.count() else '暂无可用图片，请先截取封面或补充本地图片')
            return
        image = crop_image(picture.toImage(), self.role.currentData(), self.anchor.currentData())
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(400, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
