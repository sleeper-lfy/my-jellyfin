"""Jellyfin-style media shortcuts and horizontal rows, backed exclusively by the library."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QPixmap, QColor, QLinearGradient, QFont
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QListWidget,QListWidgetItem,QAbstractItemView,QLabel,QSizePolicy


class MediaTile(QPushButton):
    def __init__(self, title, subtitle, cover, action):
        super().__init__()
        self.title, self.subtitle = title, subtitle
        self.cover = QPixmap(cover) if cover else QPixmap()
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumWidth(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(action)
        self.setAccessibleName(title)
        self.setToolTip(title)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(1, round(width * 9 / 16))

    def sizeHint(self):
        return QSize(320, 180)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(),QColor('#242424'))
        if not self.cover.isNull():
            mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if self.cover.width() > self.cover.height() else Qt.AspectRatioMode.KeepAspectRatio
            image=self.cover.scaled(self.size(),mode,Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width()-image.width())//2,(self.height()-image.height())//2,image)
        shade=QLinearGradient(0,0,0,self.height())
        shade.setColorAt(0,QColor(0,0,0,15))
        shade.setColorAt(1,QColor(0,0,0,220))
        painter.fillRect(self.rect(),shade)
        painter.setPen(QColor('white'))
        painter.setFont(QFont('Segoe UI',23,QFont.Weight.DemiBold))
        painter.drawText(self.rect().adjusted(20,0,-20,-32),Qt.AlignmentFlag.AlignBottom,self.title)
        painter.setFont(QFont('Segoe UI',10))
        painter.setPen(QColor('#cccccc'))
        painter.drawText(self.rect().adjusted(20,0,-20,-12),Qt.AlignmentFlag.AlignBottom,self.subtitle)
        if self.underMouse() or self.hasFocus():
            painter.setPen(QColor('#00a4dc'))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1,1,-1,-1))


class HomePage(QScrollArea):
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content=QWidget()
        self.layout=QVBoxLayout(self.content)
        self.layout.setContentsMargins(0,0,12,0)
        self.layout.setSpacing(12)
        self.setWidget(self.content)
        self.rows=[]

    def refresh(self):
        from .ui import clear,label,button,PosterList,PosterDelegate
        clear(self.layout)
        self.rows=[]
        works=self.window.library.query()
        self.layout.addWidget(label('我的媒体','sectionTitle'))
        tiles=QHBoxLayout()
        tiles.setSpacing(16)
        for kind,title in [('movie','电影'),('series','电视剧'),('other','其他视频')]:
            items=[w for w in works if w['kind']==kind]
            covers = [self.window.card_data(w, True) for w in items]
            cover=next((w.get('_cover') or w.get('thumbnail') for w in covers if w.get('_cover') or w.get('thumbnail')),None)
            tiles.addWidget(MediaTile(title,f'{len(items)} 部作品',cover,lambda checked=False,kind=kind:self.window.navigate(kind)))
        self.layout.addLayout(tiles)
        links=QHBoxLayout()
        for title,section in [('影片发现  ›','discover'),('观影统计  ›','stats')]:
            control=button(title,lambda checked=False,section=section:self.window.navigate(section))
            control.setObjectName('headerButton')
            links.addWidget(control)
        links.addStretch()
        self.layout.addLayout(links)
        continuing=[w for w in works if any(f['position']>0 and not f['completed'] for f in w['files'])]
        recommendations=self.window.library.recommendations()
        sections=[('继续观看',continuing,True),('最新电影',[w for w in works if w['kind']=='movie'],False),
                  ('最新电视剧',[w for w in works if w['kind']=='series'],False),('为你推荐',recommendations,False)]
        for title,items,landscape in sections:
            if not items:
                continue
            self.layout.addWidget(label(title,'sectionTitle'))
            cards=PosterList(self.window.play_work)
            cards.setObjectName('posters')
            cards.setViewMode(QListWidget.ViewMode.IconMode)
            cards.setFlow(QListWidget.Flow.LeftToRight)
            cards.setWrapping(False)
            cards.setResizeMode(QListWidget.ResizeMode.Adjust)
            cards.setMovement(QListWidget.Movement.Static)
            cards.setMouseTracking(True)
            cards.setItemDelegate(PosterDelegate(cards))
            cards.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            cards.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            landscape = landscape or self.window.view_mode.currentData() == 'thumbnail'
            cards.setFixedHeight(262 if landscape else 374)
            cards.setSpacing(2)
            for work in items[:24]:
                record=self.window.card_data(work, landscape)
                item=QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole,record)
                item.setToolTip(work['title']+'\n'+'\n'.join(work.get('reasons',[])))
                cards.addItem(item)
            cards.itemClicked.connect(self.window.open_item)
            self.rows.append(cards)
            self.layout.addWidget(cards)
        if not works:
            message=label('开始建立你的媒体库\n添加电影、电视剧或视频文件夹，封面和观看记录将在这里显示。')
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            message.setMinimumHeight(210)
            message.setStyleSheet('color: #aaaaaa; font-size: 16px;')
            self.layout.addWidget(message)
            row=QHBoxLayout()
            row.addStretch()
            row.addWidget(button('添加媒体文件夹',self.window.import_dialog,True))
            row.addStretch()
            self.layout.addLayout(row)
        self.layout.addStretch()
