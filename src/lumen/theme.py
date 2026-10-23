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

# Components share the same neutral surfaces, cyan focus and compact spacing.
STYLE += '''
QPushButton { min-height: 20px; border-radius: 5px; padding: 8px 14px; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit { min-height: 24px; border-radius: 5px; padding: 8px 10px; background: #202024; border-color: #38383d; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #00a4dc; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { padding: 4px; outline: 0; border: 1px solid #414149; }
QLabel#eyebrow { color: #90909c; font-size: 12px; }
QLabel#detailTitle { font-size: 30px; font-weight: 600; }
QLabel#sourceScore { color: #e7c567; font-weight: 600; }
QPushButton#quietAction { background: transparent; border: 1px solid transparent; padding: 6px 10px; }
QPushButton#quietAction:hover { background: #29292f; border-color: #45454d; }
QPushButton#stateAction { background: #232328; border: 1px solid #3a3a42; padding: 6px 12px; }
QPushButton#stateAction:hover { border-color: #777782; background: #303036; }
QPushButton#stateAction:checked { background: #15343f; border-color: #26738b; color: #8cdef5; }
QPushButton#favoriteAction:checked { background: #3b2029; border-color: #985166; color: #ffb1c7; }
QPushButton#favoriteAction { background: #232328; border: 1px solid #3a3a42; padding: 6px 12px; }
QPushButton#favoriteAction:hover { border-color: #c3758d; }
QPushButton#filterChip { background: #18313a; border: 1px solid #315563; border-radius: 15px; padding: 3px 10px; color: #bfe8f6; }
QPushButton#filterChip:hover { background: #254650; border-color: #62bad4; }
QPushButton#metadataChip { background: #222228; border: 1px solid #35353e; border-radius: 14px; padding: 3px 12px; color: #d6d6df; }
QPushButton#metadataChip:hover { background: #30303a; border-color: #667681; }
QPushButton#scopeChip { background: #222228; border: 1px solid #383840; border-radius: 15px; padding: 5px 12px; }
QPushButton#scopeChip:checked { background: #18323d; border-color: #30788e; color: #a0e1f5; }
QDialog#filterPanel { background: #18181d; border: 1px solid #3c3c44; }
QFrame#filterFooter { border-top: 1px solid #33333b; background: #18181d; }
QFrame#advancedFilters { background: #1e1e24; border-radius: 6px; }
QLabel#panelTitle { font-size: 23px; font-weight: 600; }
QLabel#filterLabel { color: #c7c7d1; font-size: 13px; font-weight: 500; }
QFrame#personalBar { border-top: 1px solid #35353a; }
QToolTip { border-radius: 4px; }
QMenu { border: 1px solid #41414b; padding: 5px; border-radius: 5px; }
QMenu::item { padding: 9px 24px 9px 12px; border-radius: 3px; }
QMenu::separator { height: 1px; background: #393940; margin: 5px 6px; }
'''

from pathlib import Path
_chevron=(Path(__file__).parent/'icons'/'chevron-down.svg').as_posix()
STYLE += 'QComboBox::down-arrow { image: url("'+_chevron+'"); width: 14px; height: 14px; }'
STYLE += 'QPushButton#quietAction::menu-indicator { image: none; width: 0px; } QPushButton#filterChip { border-radius: 12px; }'

STYLE += 'QPushButton#quietAction, QPushButton#stateAction, QPushButton#favoriteAction { min-height: 26px; } QPushButton#primary { min-height: 30px; }'
STYLE += 'QPushButton#resourceAction { background: #1d1d23; border-color: #37373f; text-align: left; padding: 12px 16px; } QPushButton#resourceAction:hover { border-color: #45778a; background: #262630; }'
