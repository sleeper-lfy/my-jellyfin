STYLE = '''
QFrame#header { background: #101010; border-bottom: 1px solid #222; }
QPushButton#headerButton { background: transparent; border: 0; padding: 9px 12px; border-radius: 3px; }
QPushButton#headerButton:hover { background: #303030; color: #00a4dc; }
QLabel#sectionTitle { font-size: 23px; font-weight: 500; padding-top: 8px; }
QListWidget#posters { background: transparent; border: 0; }
QPushButton#primary:hover { background: #008abd; }
QPushButton:focus { border: 1px solid #00a4dc; }

* { font-family: "Segoe UI", "Noto Sans CJK SC", sans-serif; font-size: 14px; }
QMainWindow, QDialog, QWidget#root { background: #101010; color: #eeeeee; }
QWidget { color: #eeeeee; }
QFrame#sidebar { background: #181818; border-right: 1px solid #303030; }
QLabel#brand { font-size: 25px; font-weight: 600; color: #eeeeee; padding: 4px 8px; }
QLabel#heading { font-size: 26px; font-weight: 500; }
QLabel#subtitle { color: #a0a0a0; font-size: 13px; }
QLabel#metric { font-size: 30px; font-weight: 600; color: #00a4dc; }
QPushButton { background: #292929; border: 1px solid #404040; border-radius: 3px; padding: 9px 16px; }
QPushButton:hover { background: #383838; border-color: #00a4dc; }
QPushButton:pressed { background: #444444; }
QPushButton:disabled { color: #777777; background: #202020; }
QPushButton#primary { background: #00a4dc; color: #ffffff; border: 0; font-weight: 600; }
QPushButton#nav { text-align: left; border: 0; background: transparent; padding: 13px 20px; }
QPushButton#nav:checked { background: #262626; color: #ffffff; border-left: 3px solid #00a4dc; border-radius: 0; }
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit { background: #252525; color: #ffffff; border: 1px solid #404040; border-radius: 3px; padding: 7px; selection-background-color: #00a4dc; }
QComboBox QAbstractItemView { background: #222222; selection-background-color: #333333; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: 0; }
QListWidget, QTreeWidget, QTableWidget { background: transparent; alternate-background-color: #242424; border: 0; border-radius: 8px; outline: 0; }
QListWidget::item { padding: 10px; border-radius: 6px; }
QListWidget::item:selected, QTreeWidget::item:selected { background: #333333; }
QHeaderView::section { background: #282828; color: #cccccc; border: 0; padding: 9px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: transparent; color: #aaaaaa; padding: 12px 18px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #00a4dc; }
QProgressBar { border: 0; border-radius: 3px; background: #333333; height: 6px; text-align: center; }
QProgressBar::chunk { background: #00a4dc; border-radius: 3px; }
QSlider::groove:horizontal { height: 5px; background: #444444; border-radius: 2px; }
QSlider::handle:horizontal { background: #ffffff; width: 13px; margin: -4px 0; border-radius: 6px; }
QSlider::sub-page:horizontal { background: #00a4dc; }
QGroupBox { border: 1px solid #333333; border-radius: 8px; margin-top: 20px; padding-top: 16px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #bbbbbb; }
QToolTip { background: #303030; color: #fff; border: 1px solid #555555; padding: 6px; }
QMenu { background: #252525; color: #fff; }
QMenu::item:selected { background: #404040; }
QScrollBar:vertical { width: 9px; background: transparent; }
QScrollBar::handle:vertical { background: #555555; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
'''
