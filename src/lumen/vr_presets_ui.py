"""Edit VR playback defaults for a selected media directory."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QCheckBox,
                               QComboBox, QDoubleSpinBox, QSpinBox, QDialogButtonBox, QPushButton,
                               QScrollArea,QWidget,QLineEdit)
from .vr_presets import VR_DEFAULTS, directory_path, presets, set_preset


class VrPresetDialog(QDialog):
    def __init__(self, window, path):
        super().__init__(window)
        self.window, self.path = window, directory_path(path)
        self.setWindowTitle('目录 VR 播放预设'); self.resize(560, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('应用目录（包含子目录）'))
        path_label = QLineEdit(str(self.path));path_label.setObjectName('presetDirectory');path_label.setReadOnly(True);path_label.setToolTip(str(self.path));layout.addWidget(path_label)
        scroll=QScrollArea();scroll.setObjectName('vrPresetFields');scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body=QWidget();content=QVBoxLayout(body);scroll.setWidget(body);layout.addWidget(scroll,1)
        note = QLabel('适用于此目录及子目录的视频。更具体的子目录预设优先；单片手动设置优先。\n修改后在下次打开视频时生效。当前 Android 播放器支持 VR180 左右 3D，不包含 VR360 或上下格式转换。')
        note.setWordWrap(True); content.addWidget(note)
        own = next((entry['vr'] for entry in presets(window.library) if directory_path(entry['path']) == self.path), {})
        values = {**VR_DEFAULTS, **own}; form = QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);content.addLayout(form)
        self.fields = {}
        projection = QComboBox(); projection.addItem('标准等距柱状投影', False); projection.addItem('鱼眼投影', True)
        projection.setCurrentIndex(1 if values['fish'] else 0); self.fields['fish'] = projection; form.addRow('投影方式', projection)
        for key, title in [('headset', '双眼观看（关闭为单屏左眼预览）'), ('swap', '交换左右眼'),
                           ('tracking', '陀螺仪转向'), ('swipe_seek', '单指横滑调进度'),
                           ('tracking_invert_pitch', '反转陀螺仪上下方向')]:
            field = QCheckBox(title); field.setChecked(values[key]); self.fields[key] = field; form.addRow(field)
        for key, title, low, high, suffix in [('fov', '视场角', 50, 110, '°'), ('yaw', '初始水平朝向', -180, 180, '°'),
                                             ('pitch', '初始垂直朝向', -85, 85, '°'), ('tracking_smoothing', '陀螺仪平滑', 0, 150, ' ms')]:
            field = QSpinBox(); field.setRange(low, high); field.setValue(round(values[key])); field.setSuffix(suffix)
            self.fields[key] = field; form.addRow(title, field)
        sensitivity = QDoubleSpinBox(); sensitivity.setRange(.25, 1.5); sensitivity.setSingleStep(.05); sensitivity.setValue(values['tracking_sensitivity'])
        self.fields['tracking_sensitivity'] = sensitivity; form.addRow('陀螺仪灵敏度', sensitivity)
        remove = QPushButton('移除此目录预设');remove.setToolTip('恢复上级目录或默认参数，保留单片手动设置');remove.clicked.connect(self.remove);content.addWidget(remove);content.addStretch()
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存'); buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def save(self):
        values = {key: field.currentData() if isinstance(field, QComboBox) else field.isChecked() if isinstance(field, QCheckBox) else field.value()
                  for key, field in self.fields.items()}
        try: set_preset(self.window.library, self.path, values)
        except (ValueError, OSError) as error: self.status.setText(str(error)); return
        self.window.status.setText('目录 VR 预设已保存，下次打开视频时生效'); self.accept()
    def remove(self):
        set_preset(self.window.library, self.path, None)
        self.window.status.setText('已移除此目录 VR 预设，单片设置保持'); self.accept()


def show_vr_presets(window, path):
    dialog = VrPresetDialog(window, path); result = dialog.exec(); dialog.deleteLater(); return result
