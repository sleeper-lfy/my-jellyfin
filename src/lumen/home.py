"""Jellyfin-style media shortcuts and horizontal rows, backed exclusively by the library."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QPixmap, QColor, QLinearGradient, QFont
from PySide6.QtWidgets import QScrollArea,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QListWidget,QListWidgetItem,QAbstractItemView,QLabel,QSizePolicy


class MediaTile(QPushButton):
    def __init__(self, title, subtitle, cover, action):
        super().__init__()
        self.title, self.subtitle = title, subtitle
        self.cover_path=cover
        from .images import image_cache
        image_cache().changed.connect(self.update)
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
        from .images import image_cache
        cover=image_cache().request(self.cover_path,QSize(960,540))
        if not cover.isNull():
            mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if cover.width() > cover.height() else Qt.AspectRatioMode.KeepAspectRatio
            image=cover.scaled(self.size(),mode,Qt.TransformationMode.SmoothTransformation)
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
        from .ui import label,button,PosterList,PosterDelegate
        self.window=window
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content=QWidget();self.layout=QVBoxLayout(self.content)
        self.layout.setContentsMargins(0,0,12,0);self.layout.setSpacing(12)
        self.setWidget(self.content);self.rows=[];self.tiles={};self.sections={}
        self.layout.addWidget(label('我的媒体','sectionTitle'))
        tiles=QHBoxLayout();tiles.setSpacing(16)
        for kind,title in [('movie','电影'),('series','电视剧'),('vr','VR电影'),('fans','Fans'),('other','其他视频')]:
            tile=MediaTile(title,'0 位作者' if kind=='fans' else '0 部作品',None,lambda checked=False,kind=kind:window.navigate(kind))
            self.tiles[kind]=tile;tiles.addWidget(tile)
        self.layout.addLayout(tiles)
        links=QHBoxLayout()
        for title,section in [('为我推荐  ›','recommend'),('影片发现  ›','discover'),('观影统计  ›','stats')]:
            control=button(title,lambda checked=False,section=section:window.navigate(section));control.setObjectName('headerButton');links.addWidget(control)
        links.addStretch();self.layout.addLayout(links)
        for title in ['继续观看','最新电影','最新电视剧','最新VR电影','最新Fans作者','为你推荐']:
            heading=label(title,'sectionTitle');self.layout.addWidget(heading)
            cards=PosterList(window.play_work)
            cards.favoriteRequested.connect(window.toggle_favorite)
            cards.watchlistRequested.connect(lambda work_id:window.toggle_card_personal(work_id,'watchlist'))
            cards.setObjectName('posters');cards.setViewMode(QListWidget.ViewMode.IconMode);cards.setFlow(QListWidget.Flow.LeftToRight)
            cards.setWrapping(False);cards.setResizeMode(QListWidget.ResizeMode.Adjust);cards.setMovement(QListWidget.Movement.Static)
            cards.setMouseTracking(True);cards.setItemDelegate(PosterDelegate(cards));cards.setSpacing(2)
            cards.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            cards.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded);cards.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            cards.itemClicked.connect(window.open_item);self.layout.addWidget(cards);self.sections[title]=(heading,cards)
        self.empty=QWidget();empty_layout=QVBoxLayout(self.empty)
        message=label('开始建立你的媒体库\n添加电影、电视剧或视频文件夹，封面和观看记录将在这里显示。')
        message.setAlignment(Qt.AlignmentFlag.AlignCenter);message.setMinimumHeight(210);message.setStyleSheet('color: #aaaaaa; font-size: 16px;')
        empty_layout.addWidget(message);row=QHBoxLayout();row.addStretch();row.addWidget(button('添加媒体文件夹',window.import_dialog,True));row.addStretch();empty_layout.addLayout(row)
        self.layout.addWidget(self.empty);self.layout.addStretch()

    def refresh(self,works=None,recommendations=None):
        from .ui import update_poster_items
        if works is None:works=self.window.library.query()
        position=self.verticalScrollBar().value()
        for kind,tile in self.tiles.items():
            items=[work for work in works if work['kind']==kind];cover=None
            for work in items[:24]:
                record=self.window.card_data(work,True);cover=record.get('_cover') or record.get('thumbnail')
                if cover:break
            tile.subtitle=f'{len(items)} 位作者' if kind=='fans' else f'{len(items)} 部作品';tile.cover_path=cover;tile.update()
        continuing=[work for work in works if any(file['position']>0 and not file['completed'] for file in work['files'])]
        if recommendations is None:recommendations=self.window.library.recommendations()
        sections=[('继续观看',continuing,True),('最新电影',[work for work in works if work['kind']=='movie'],False),
                  ('最新电视剧',[work for work in works if work['kind']=='series'],False),('最新VR电影',[work for work in works if work['kind']=='vr'],False),('最新Fans作者',[work for work in works if work['kind']=='fans'],False),('为你推荐',recommendations,False)]
        self.rows=[]
        for title,items,landscape in sections:
            heading,cards=self.sections[title];landscape=landscape or self.window.view_mode.currentData()=='thumbnail'
            cards.setFixedHeight(262 if landscape else 374)
            update_poster_items(cards,[self.window.card_data(work,landscape) for work in items[:24]])
            heading.setVisible(bool(items));cards.setVisible(bool(items))
            if items:self.rows.append(cards)
        self.empty.setVisible(not works);self.layout.activate();self.verticalScrollBar().setValue(position)
